"""Llamadas entrantes P1 → tablets (WebSocket, primera en contestar gana)."""
from __future__ import annotations

import asyncio
import logging
import queue
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

from app.core.config import settings
from app.db.tablet_config_store import get_tablet_call_settings

log = logging.getLogger("tablet.call")

DOOR_LABELS: dict[str, str] = {
    "p1": "Puerta calle (P1)",
    "p2": "Puerta oficina (P2)",
}


@dataclass
class TabletClient:
    client_id: str
    ws: WebSocket
    username: str
    connected_at: float = field(default_factory=time.monotonic)


@dataclass
class ActiveCall:
    call_id: str
    door: str
    pulsador: str
    mode: str
    started_at: float
    timeout_task: Optional[asyncio.Task[Any]] = None
    answered_by: Optional[str] = None
    answered_username: Optional[str] = None
    rejected_clients: set[str] = field(default_factory=set)


_clients: dict[str, TabletClient] = {}
_active_call: Optional[ActiveCall] = None
_intercom_holder_id: Optional[str] = None
_intercom_holder_username: Optional[str] = None
_intercom_door: Optional[str] = None
_lock = asyncio.Lock()
_pending_broadcasts: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)


def _tablet_call_cfg() -> dict:
    try:
        return get_tablet_call_settings()
    except Exception:  # noqa: BLE001
        return {}


def _tablet_call_enabled() -> bool:
    tc = _tablet_call_cfg()
    if "enabled" in tc:
        return bool(tc["enabled"])
    return bool(settings.tablet_call_enabled)


def _tablet_call_modes() -> frozenset[str]:
    tc = _tablet_call_cfg()
    raw = (tc.get("modes") if tc.get("modes") is not None else settings.tablet_call_modes) or ""
    raw = str(raw).strip()
    if not raw:
        return frozenset()
    return frozenset(m.strip() for m in raw.split(",") if m.strip())


def _tablet_call_pulsadores() -> frozenset[str]:
    tc = _tablet_call_cfg()
    raw = (tc.get("pulsadores") if tc.get("pulsadores") is not None else settings.tablet_call_pulsadores) or "p1"
    raw = str(raw).strip()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _tablet_call_timeout_seconds() -> int:
    tc = _tablet_call_cfg()
    if tc.get("timeoutSeconds") is not None:
        try:
            return max(5, int(tc["timeoutSeconds"]))
        except (TypeError, ValueError):
            pass
    return max(5, int(settings.tablet_call_timeout_seconds))


def should_start_tablet_call(pulsador: str, panel_mode: Optional[str]) -> bool:
    if not _tablet_call_enabled():
        return False
    if not panel_mode or panel_mode not in _tablet_call_modes():
        return False
    return pulsador in _tablet_call_pulsadores()


def _call_remaining_seconds(call: ActiveCall) -> int:
    return max(
        0,
        int(_tablet_call_timeout_seconds() - (time.monotonic() - call.started_at)),
    )


def _is_call_expired(call: ActiveCall) -> bool:
    return _call_remaining_seconds(call) <= 0


async def _purge_stale_active_call() -> Optional[str]:
    """Elimina llamadas caducadas que el timeout no llegó a limpiar."""
    global _active_call
    async with _lock:
        call = _active_call
        if not call or call.answered_by is not None:
            return None
        if not _is_call_expired(call):
            return None
        call_id = call.call_id
        if call.timeout_task and not call.timeout_task.done():
            call.timeout_task.cancel()
        _active_call = None
    log.info("Llamada tablet expirada (purge) call_id=%s", call_id)
    return call_id


def publish_sync(message: dict[str, Any]) -> None:
    """Encola broadcast para el pump asyncio (desde código síncrono del panel)."""
    try:
        _pending_broadcasts.put_nowait(message)
    except queue.Full:
        log.warning("Tablet WS cola llena, evento descartado: %s", message.get("type"))


async def pump_loop() -> None:
    while True:
        await asyncio.sleep(0.05)
        batch: list[dict[str, Any]] = []
        for _ in range(50):
            try:
                batch.append(_pending_broadcasts.get_nowait())
            except queue.Empty:
                break
        for msg in batch:
            await _broadcast(msg)


def notify_toggle_rules_changed(active_toggle_rules: list[str]) -> None:
    publish_sync(
        {
            "type": "toggle_rules_changed",
            "active_toggle_rules": active_toggle_rules,
        }
    )


def notify_mode_changed(current_mode: Optional[str]) -> None:
    publish_sync(
        {
            "type": "mode_changed",
            "current_mode": current_mode,
        }
    )


def notify_mode_queued(
    pending_mode: Optional[str],
    blocked_inputs: Optional[list[str]] = None,
) -> None:
    publish_sync(
        {
            "type": "mode_queued",
            "pending_mode": pending_mode,
            "blocked_inputs": blocked_inputs or [],
        }
    )


def notify_coce_message(message: dict[str, Any]) -> None:
    publish_sync(
        {
            "type": "coce_notification",
            "id": message.get("id"),
            "title": message.get("title"),
            "body": message.get("body"),
            "urgent": bool(message.get("urgent")),
            "received_at": message.get("received_at"),
        }
    )


async def register(client_id: str, ws: WebSocket, username: str) -> None:
    async with _lock:
        old = _clients.get(client_id)
        if old is not None and old.ws is not ws:
            _clients.pop(client_id, None)
        _clients[client_id] = TabletClient(client_id=client_id, ws=ws, username=username)
    log.info("Tablet WS registrada id=%s user=%s (total=%s)", client_id, username, len(_clients))
    await _purge_stale_active_call()
    await _send_to_client(client_id, _intercom_status_message())
    try:
        from app.api.routes import panel as panel_routes

        status = panel_routes.api_v1_get_mode_status()
        await _send_to_client(
            client_id,
            {"type": "mode_changed", "current_mode": status.get("current_mode")},
        )
        await _send_to_client(
            client_id,
            {
                "type": "toggle_rules_changed",
                "active_toggle_rules": status.get("active_toggle_rules") or [],
            },
        )
        pending = status.get("pending_mode")
        if pending:
            await _send_to_client(
                client_id,
                {"type": "mode_queued", "pending_mode": pending, "blocked_inputs": []},
            )
    except Exception:  # noqa: BLE001
        pass
    call = _active_call
    if (
        call
        and call.answered_by is None
        and client_id not in call.rejected_clients
        and not _is_call_expired(call)
    ):
        await _send_to_client(client_id, _incoming_call_message(call))


async def unregister(client_id: str) -> None:
    global _intercom_holder_id, _intercom_holder_username, _intercom_door
    async with _lock:
        _clients.pop(client_id, None)
        if _intercom_holder_id == client_id:
            _intercom_holder_id = None
            _intercom_holder_username = None
            _intercom_door = None
    log.info("Tablet WS desconectada id=%s (total=%s)", client_id, len(_clients))
    await _broadcast_intercom_status()


def _incoming_call_message(call: ActiveCall) -> dict[str, Any]:
    remaining = _call_remaining_seconds(call)
    return {
        "type": "incoming_call",
        "call_id": call.call_id,
        "door": call.door,
        "door_label": DOOR_LABELS.get(call.door, call.door.upper()),
        "pulsador": call.pulsador,
        "mode": call.mode,
        "timeout_seconds": _tablet_call_timeout_seconds(),
        "remaining_seconds": remaining,
    }


def _intercom_status_message() -> dict[str, Any]:
    busy = _intercom_holder_id is not None
    return {
        "type": "intercom_status",
        "busy": busy,
        "door": _intercom_door,
        "holder_username": _intercom_holder_username if busy else None,
    }


async def _send_to_client(client_id: str, message: dict[str, Any]) -> bool:
    client = _clients.get(client_id)
    if not client:
        return False
    try:
        await client.ws.send_json(message)
        return True
    except Exception:  # noqa: BLE001
        return False


async def _broadcast(
    message: dict[str, Any],
    *,
    exclude: Optional[set[str]] = None,
    only: Optional[set[str]] = None,
) -> None:
    dead: list[str] = []
    for cid, client in list(_clients.items()):
        if exclude and cid in exclude:
            continue
        if only is not None and cid not in only:
            continue
        try:
            await client.ws.send_json(message)
        except Exception:  # noqa: BLE001
            dead.append(cid)
    for cid in dead:
        _clients.pop(cid, None)


async def _broadcast_intercom_status() -> None:
    await _broadcast(_intercom_status_message())


async def _cancel_call_timeout(call: ActiveCall) -> None:
    global _active_call
    try:
        await asyncio.sleep(max(1, _tablet_call_timeout_seconds()))
    except asyncio.CancelledError:
        return
    async with _lock:
        if _active_call is not call or call.answered_by is not None:
            return
        call_id = call.call_id
        _active_call = None
    log.info("Llamada tablet expirada call_id=%s", call_id)
    await _broadcast(
        {"type": "call_cancelled", "call_id": call_id, "reason": "timeout"},
        exclude=call.rejected_clients,
    )


async def start_call(*, door: str, pulsador: str, mode: str) -> dict[str, Any]:
    global _active_call
    replaced_call_id: Optional[str] = None
    replaced_rejected: set[str] = set()
    async with _lock:
        if _active_call and _active_call.answered_by is None:
            old = _active_call
            replaced_call_id = old.call_id
            replaced_rejected = set(old.rejected_clients)
            if old.timeout_task and not old.timeout_task.done():
                old.timeout_task.cancel()

        call_id = uuid.uuid4().hex
        call = ActiveCall(
            call_id=call_id,
            door=door,
            pulsador=pulsador,
            mode=mode,
            started_at=time.monotonic(),
        )
        call.timeout_task = asyncio.create_task(_cancel_call_timeout(call))
        _active_call = call

    if replaced_call_id:
        await _broadcast(
            {
                "type": "call_cancelled",
                "call_id": replaced_call_id,
                "reason": "replaced",
            },
            exclude=replaced_rejected,
        )

    msg = _incoming_call_message(call)
    targets = {cid for cid in _clients if cid not in call.rejected_clients}
    await _broadcast(msg, only=targets if targets else None)
    log.info(
        "Llamada tablet iniciada call_id=%s door=%s mode=%s tablets=%s",
        call_id,
        door,
        mode,
        len(targets),
    )
    return {
        "started": True,
        "call_id": call_id,
        "tablets_notified": len(targets),
    }


async def handle_client_message(client_id: str, data: dict[str, Any]) -> None:
    msg_type = data.get("type")
    if msg_type == "ping":
        await _send_to_client(client_id, {"type": "pong"})
        return

    if msg_type == "answer":
        await _answer_call(client_id, str(data.get("call_id") or ""))
        return

    if msg_type == "reject":
        await _reject_call(client_id, str(data.get("call_id") or ""))
        return

    if msg_type == "intercom_claim":
        door = str(data.get("door") or "p1").lower()
        await _claim_intercom(client_id, door)
        return

    if msg_type == "intercom_release":
        await _release_intercom(client_id)
        return


async def _answer_call(client_id: str, call_id: str) -> None:
    global _active_call
    error_msg: Optional[dict[str, Any]] = None
    taken_msg: Optional[dict[str, Any]] = None
    accepted_msg: Optional[dict[str, Any]] = None
    broadcast_taken: Optional[dict[str, Any]] = None
    other_clients: set[str] = set()

    async with _lock:
        call = _active_call
        if not call or call.call_id != call_id:
            error_msg = {"type": "call_error", "call_id": call_id, "reason": "not_found"}
        elif call.answered_by is not None:
            taken_msg = {
                "type": "call_taken",
                "call_id": call_id,
                "answered_by": call.answered_username,
            }
        elif client_id in call.rejected_clients:
            error_msg = {"type": "call_error", "call_id": call_id, "reason": "rejected"}
        else:
            client = _clients.get(client_id)
            if not client:
                return
            call.answered_by = client_id
            call.answered_username = client.username
            if call.timeout_task and not call.timeout_task.done():
                call.timeout_task.cancel()
            door = call.door
            answered_username = client.username
            other_clients = {cid for cid in _clients if cid != client_id}
            _active_call = None
            accepted_msg = {
                "type": "call_accepted",
                "call_id": call_id,
                "door": door,
                "door_label": DOOR_LABELS.get(door, door.upper()),
            }
            broadcast_taken = {
                "type": "call_taken",
                "call_id": call_id,
                "answered_by": answered_username,
            }

    if error_msg:
        await _send_to_client(client_id, error_msg)
        return
    if taken_msg:
        await _send_to_client(client_id, taken_msg)
        return
    if not accepted_msg:
        return

    await _send_to_client(client_id, accepted_msg)
    if broadcast_taken and other_clients:
        await _broadcast(broadcast_taken, only=other_clients)
    log.info(
        "Llamada contestada call_id=%s door=%s client=%s",
        call_id,
        accepted_msg.get("door"),
        client_id,
    )


async def _reject_call(client_id: str, call_id: str) -> None:
    async with _lock:
        call = _active_call
        if not call or call.call_id != call_id or call.answered_by is not None:
            return
        call.rejected_clients.add(client_id)
    await _send_to_client(client_id, {"type": "call_dismissed", "call_id": call_id})
    log.debug("Tablet %s rechazó llamada %s", client_id, call_id)


async def _claim_intercom(client_id: str, door: str) -> None:
    global _intercom_holder_id, _intercom_holder_username, _intercom_door
    busy_response: Optional[dict[str, Any]] = None
    async with _lock:
        if _intercom_holder_id and _intercom_holder_id != client_id:
            holder = _intercom_holder_username or "otra tablet"
            busy_response = {
                "type": "intercom_busy",
                "door": _intercom_door,
                "holder_username": holder,
            }
        else:
            client = _clients.get(client_id)
            _intercom_holder_id = client_id
            _intercom_holder_username = client.username if client else None
            _intercom_door = door
    if busy_response:
        await _send_to_client(client_id, busy_response)
        return
    await _send_to_client(client_id, {"type": "intercom_claimed", "door": door})
    await _broadcast_intercom_status()


async def _release_intercom(client_id: str) -> None:
    global _intercom_holder_id, _intercom_holder_username, _intercom_door
    async with _lock:
        if _intercom_holder_id != client_id:
            return
        _intercom_holder_id = None
        _intercom_holder_username = None
        _intercom_door = None
    await _broadcast_intercom_status()


def is_intercom_busy_for(client_id: Optional[str] = None) -> bool:
    if _intercom_holder_id is None:
        return False
    if client_id and _intercom_holder_id == client_id:
        return False
    return True


def get_snapshot() -> dict[str, Any]:
    call = _active_call
    return {
        "clients": len(_clients),
        "active_call": (
            {
                "call_id": call.call_id,
                "door": call.door,
                "answered_by": call.answered_username,
            }
            if call
            else None
        ),
        "intercom_busy": _intercom_holder_id is not None,
        "intercom_holder": _intercom_holder_username,
        "intercom_door": _intercom_door,
    }
