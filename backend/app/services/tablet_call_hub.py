"""Llamadas entrantes P1 → tablets (WebSocket, primera en contestar gana)."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

from app.core.config import settings

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


def _tablet_call_modes() -> frozenset[str]:
    raw = (settings.tablet_call_modes or "").strip()
    if not raw:
        return frozenset()
    return frozenset(m.strip() for m in raw.split(",") if m.strip())


def _tablet_call_pulsadores() -> frozenset[str]:
    raw = (settings.tablet_call_pulsadores or "p1").strip()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def should_start_tablet_call(pulsador: str, panel_mode: Optional[str]) -> bool:
    if not settings.tablet_call_enabled:
        return False
    if not panel_mode or panel_mode not in _tablet_call_modes():
        return False
    return pulsador in _tablet_call_pulsadores()


async def register(client_id: str, ws: WebSocket, username: str) -> None:
    async with _lock:
        old = _clients.get(client_id)
        if old is not None and old.ws is not ws:
            _clients.pop(client_id, None)
        _clients[client_id] = TabletClient(client_id=client_id, ws=ws, username=username)
    log.info("Tablet WS registrada id=%s user=%s (total=%s)", client_id, username, len(_clients))
    await _send_to_client(client_id, _intercom_status_message())
    call = _active_call
    if call and call.answered_by is None and client_id not in call.rejected_clients:
        await _send_to_client(client_id, _incoming_call_message(call))


async def unregister(client_id: str) -> None:
    async with _lock:
        _clients.pop(client_id, None)
        if _intercom_holder_id == client_id:
            _intercom_holder_id = None
            _intercom_holder_username = None
            _intercom_door = None
    log.info("Tablet WS desconectada id=%s (total=%s)", client_id, len(_clients))
    await _broadcast_intercom_status()


def _incoming_call_message(call: ActiveCall) -> dict[str, Any]:
    remaining = max(
        0,
        int(settings.tablet_call_timeout_seconds - (time.monotonic() - call.started_at)),
    )
    return {
        "type": "incoming_call",
        "call_id": call.call_id,
        "door": call.door,
        "door_label": DOOR_LABELS.get(call.door, call.door.upper()),
        "pulsador": call.pulsador,
        "mode": call.mode,
        "timeout_seconds": settings.tablet_call_timeout_seconds,
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
    try:
        await asyncio.sleep(max(1, settings.tablet_call_timeout_seconds))
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
    async with _lock:
        call = _active_call
        if not call or call.call_id != call_id:
            await _send_to_client(
                client_id,
                {"type": "call_error", "call_id": call_id, "reason": "not_found"},
            )
            return
        if call.answered_by is not None:
            await _send_to_client(
                client_id,
                {
                    "type": "call_taken",
                    "call_id": call_id,
                    "answered_by": call.answered_username,
                },
            )
            return
        if client_id in call.rejected_clients:
            await _send_to_client(
                client_id,
                {"type": "call_error", "call_id": call_id, "reason": "rejected"},
            )
            return

        client = _clients.get(client_id)
        if not client:
            return

        call.answered_by = client_id
        call.answered_username = client.username
        if call.timeout_task and not call.timeout_task.done():
            call.timeout_task.cancel()

        answered_username = client.username
        door = call.door
        other_clients = {cid for cid in _clients if cid != client_id}
        _active_call = None

    await _send_to_client(
        client_id,
        {
            "type": "call_accepted",
            "call_id": call_id,
            "door": door,
            "door_label": DOOR_LABELS.get(door, door.upper()),
        },
    )
    await _broadcast(
        {
            "type": "call_taken",
            "call_id": call_id,
            "answered_by": answered_username,
        },
        only=other_clients,
    )
    log.info("Llamada contestada call_id=%s por %s (%s)", call_id, answered_username, client_id)


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
