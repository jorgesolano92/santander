"""Estado en vivo por sucursal y fan-out al dashboard (solo si hay viewers)."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

from app.core.config import settings

log = logging.getLogger("coce.live_hub")

BranchStatus = str  # operativo | no_operativo | apagado


@dataclass
class BranchLiveState:
    installation_id: str
    nombre: str = ""
    ws_connected: bool = False
    last_heartbeat_ts: float = 0.0
    last_event_ts: float = 0.0
    modbus: bool = False
    boards_connected: int = 0
    boards_total: int = 0
    current_mode: Optional[str] = None
    partial: dict[str, Any] = field(default_factory=dict)
    last_broadcast_status: Optional[BranchStatus] = None

    def to_public(self, status: BranchStatus) -> dict[str, Any]:
        return {
            "installationId": self.installation_id,
            "nombre": self.nombre,
            "status": status,
            "wsConnected": self.ws_connected,
            "modbus": self.modbus,
            "boardsConnected": self.boards_connected,
            "boardsTotal": self.boards_total,
            "currentMode": self.current_mode,
            "lastHeartbeatTs": self.last_heartbeat_ts or None,
            "lastEventTs": self.last_event_ts or None,
            "partial": self.partial or None,
        }


class LiveHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._states: dict[str, BranchLiveState] = {}
        self._branch_ws: dict[str, WebSocket] = {}
        self._dashboard_ws: set[WebSocket] = set()
        self._viewer_count = 0

    @property
    def viewer_count(self) -> int:
        return self._viewer_count

    def _timeout_s(self) -> float:
        return float(settings.branch_heartbeat_timeout_seconds)

    def _heartbeat_fresh(self, st: BranchLiveState, now: float | None = None) -> bool:
        ts = now if now is not None else time.time()
        return bool(
            st.last_heartbeat_ts
            and (ts - st.last_heartbeat_ts) <= self._timeout_s()
        )

    def derive_status(self, st: BranchLiveState) -> BranchStatus:
        if not st.ws_connected or not self._heartbeat_fresh(st):
            return "apagado"
        if st.modbus and st.boards_connected > 0:
            return "operativo"
        return "no_operativo"

    @staticmethod
    def _clear_stale_branch_data(st: BranchLiveState) -> None:
        st.modbus = False
        st.boards_connected = 0
        st.boards_total = 0
        st.partial = {}

    async def ensure_branch(self, installation_id: str, nombre: str = "") -> BranchLiveState:
        async with self._lock:
            st = self._states.get(installation_id)
            if not st:
                st = BranchLiveState(installation_id=installation_id, nombre=nombre)
                self._states[installation_id] = st
            elif nombre and not st.nombre:
                st.nombre = nombre
            return st

    async def register_branch_ws(self, installation_id: str, ws: WebSocket, nombre: str = "") -> None:
        async with self._lock:
            old = self._branch_ws.get(installation_id)
            if old is not None and old is not ws:
                try:
                    await old.close(code=4000, reason="replaced")
                except Exception:  # noqa: BLE001
                    pass
            self._branch_ws[installation_id] = ws
            st = self._states.get(installation_id) or BranchLiveState(
                installation_id=installation_id, nombre=nombre
            )
            st.ws_connected = True
            st.nombre = nombre or st.nombre
            self._states[installation_id] = st

    async def unregister_branch_ws(self, installation_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if self._branch_ws.get(installation_id) is ws:
                del self._branch_ws[installation_id]
            st = self._states.get(installation_id)
            if st:
                st.ws_connected = False
                self._clear_stale_branch_data(st)
        await self._maybe_broadcast(installation_id)

    async def register_dashboard(self, ws: WebSocket) -> None:
        async with self._lock:
            self._dashboard_ws.add(ws)
            self._viewer_count = len(self._dashboard_ws)

    async def unregister_dashboard(self, ws: WebSocket) -> None:
        async with self._lock:
            self._dashboard_ws.discard(ws)
            self._viewer_count = len(self._dashboard_ws)

    async def ingest(self, installation_id: str, message: dict[str, Any], nombre: str = "") -> None:
        msg_type = str(message.get("type") or "event")
        payload = message.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        event: dict[str, Any] | None = None
        async with self._lock:
            st = self._states.get(installation_id) or BranchLiveState(
                installation_id=installation_id, nombre=nombre
            )
            if nombre:
                st.nombre = nombre
            now = time.time()
            st.last_event_ts = now

            if msg_type == "heartbeat":
                st.last_heartbeat_ts = now
                st.modbus = bool(payload.get("modbus"))
                st.boards_connected = int(payload.get("boards_connected") or 0)
                st.boards_total = int(payload.get("boards_total") or 0)
                if "current_mode" in payload:
                    st.current_mode = payload.get("current_mode")
            elif msg_type == "mode_changed":
                st.current_mode = payload.get("current_mode")
                st.partial = {
                    **(st.partial or {}),
                    "currentMode": st.current_mode,
                }
            elif msg_type == "branch_alert":
                alerts = dict((st.partial or {}).get("alerts") or {})
                alert_type = str(payload.get("alert_type") or "unknown")
                if payload.get("active"):
                    alerts[alert_type] = payload
                else:
                    alerts.pop(alert_type, None)
                st.partial = {**(st.partial or {}), "alerts": alerts}
                try:
                    from app.db import alerts_store as alerts_store

                    alerts_store.record_alert_event(
                        branch_id=installation_id,
                        branch_nombre=st.nombre or nombre or installation_id,
                        alert_type=alert_type,
                        active=bool(payload.get("active")),
                        message=str(payload.get("message") or ""),
                        detail=payload,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("branch_alert persist failed: %s", exc)
            elif msg_type == "toggle_rules_changed":
                st.partial = {
                    **(st.partial or {}),
                    "active_toggle_rules": payload.get("active_toggle_rules") or [],
                }
            elif msg_type in ("output_changed", "input_override", "board_connected", "board_disconnected"):
                st.partial = payload
            elif msg_type in ("snapshot", "panel_status"):
                st.modbus = bool(payload.get("modbus"))
                st.boards_connected = int(payload.get("boards_connected") or 0)
                st.boards_total = int(payload.get("boards_total") or 0)
                st.current_mode = payload.get("current_mode")
                st.partial = {
                    **(st.partial or {}),
                    **payload,
                    "currentMode": payload.get("current_mode"),
                    "active_toggle_rules": payload.get("active_toggle_rules") or [],
                }
            elif msg_type == "update_status":
                # Persistencia de despliegue; se reenvía al dashboard en branch_update.message
                try:
                    from app.db import updates_store as updates_store

                    rid = str(payload.get("release_id") or "")
                    status = str(payload.get("status") or "")
                    if rid and status:
                        updates_store.update_deployment_status(
                            release_id=rid,
                            branch_id=installation_id,
                            status=status,
                            error=str(payload.get("error") or "") or None,
                        )
                except Exception as exc:  # noqa: BLE001
                    log.warning("update_status persist failed: %s", exc)
                st.partial = {
                    **(st.partial or {}),
                    "lastUpdateStatus": payload,
                }
            elif msg_type == "message_ack":
                try:
                    from app.db import messages_store as messages_store

                    mid = str(payload.get("id") or payload.get("message_id") or "")
                    if mid:
                        messages_store.mark_read(
                            mid,
                            read_by=str(
                                payload.get("read_by")
                                or payload.get("channel")
                                or "branch"
                            ),
                            read_at=str(payload.get("read_at") or "") or None,
                        )
                except Exception as exc:  # noqa: BLE001
                    log.warning("message_ack persist failed: %s", exc)
                st.partial = {
                    **(st.partial or {}),
                    "lastMessageAck": payload,
                }

            self._states[installation_id] = st
            event = self._branch_update_event(installation_id, st, msg_type, payload)
            if event:
                st.last_broadcast_status = event["status"]

        if event:
            await self._broadcast(event)

    def _branch_update_event(
        self,
        installation_id: str,
        st: BranchLiveState,
        msg_type: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        status = self.derive_status(st)
        if status == st.last_broadcast_status and msg_type is None:
            return None
        event: dict[str, Any] = {
            "type": "branch_update",
            "installationId": installation_id,
            "status": status,
            "branch": st.to_public(status),
        }
        if msg_type is not None:
            event["message"] = {"type": msg_type, "payload": payload or {}}
        return event

    async def _maybe_broadcast(self, installation_id: str) -> None:
        event: dict[str, Any] | None = None
        async with self._lock:
            st = self._states.get(installation_id)
            if not st:
                return
            event = self._branch_update_event(installation_id, st)
            if event:
                st.last_broadcast_status = event["status"]
        if event:
            await self._broadcast(event)

    async def status_sweep_loop(self) -> None:
        interval = min(15.0, max(5.0, self._timeout_s() / 6))
        while True:
            try:
                await asyncio.sleep(interval)
                await self._sweep_statuses()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("status sweep: %s", e)

    async def _sweep_statuses(self) -> None:
        if self._viewer_count <= 0:
            return
        events: list[dict[str, Any]] = []
        async with self._lock:
            for installation_id, st in self._states.items():
                event = self._branch_update_event(installation_id, st)
                if event:
                    st.last_broadcast_status = event["status"]
                    events.append(event)
        for event in events:
            await self._broadcast(event)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        if self._viewer_count <= 0:
            return
        async with self._lock:
            clients = list(self._dashboard_ws)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.unregister_dashboard(ws)

    async def snapshot_for_dashboard(self) -> dict[str, Any]:
        async with self._lock:
            items = []
            for iid, st in self._states.items():
                status = self.derive_status(st)
                items.append(st.to_public(status))
            return {"type": "live_snapshot", "branches": items}

    async def send_to_branch(self, installation_id: str, message: dict[str, Any]) -> bool:
        async with self._lock:
            ws = self._branch_ws.get(installation_id)
        if not ws:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("send_to_branch %s: %s", installation_id, e)
            return False


live_hub = LiveHub()
