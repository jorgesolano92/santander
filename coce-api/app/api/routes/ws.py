"""WebSockets: ingest sucursal y live dashboard."""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.db import branches_store as branches
from app.services.jwt_service import decode_token
from app.services.live_hub import live_hub

log = logging.getLogger("coce.ws")
router = APIRouter(tags=["WebSocket"])


def _verify_ingest(installation_id: str, token: Optional[str]) -> tuple[bool, str]:
    row = branches.get_branch(installation_id)
    if not row:
        return False, ""
    nombre = row.get("nombre") or ""
    if not settings.branch_auth_required:
        return True, nombre
    if not token:
        return False, nombre
    if branches.verify_ingest_token(installation_id, token):
        return True, nombre
    return False, nombre


@router.websocket("/ws/branch/{installation_id}")
async def ws_branch_ingest(
    websocket: WebSocket,
    installation_id: str,
    token: Annotated[Optional[str], Query()] = None,
) -> None:
    hdr = websocket.headers.get("x-coce-ingest-token")
    ingest_token = token or hdr
    ok, nombre = _verify_ingest(installation_id, ingest_token)
    if not ok:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await live_hub.register_branch_ws(installation_id, websocket, nombre=nombre)
    log.info("WS sucursal conectada: %s", installation_id)
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict):
                log.info(
                    "ingest %s type=%s",
                    installation_id,
                    data.get("type"),
                )
                await live_hub.ingest(installation_id, data, nombre=nombre)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("WS sucursal %s: %s", installation_id, e)
    finally:
        await live_hub.unregister_branch_ws(installation_id, websocket)
        log.info("WS sucursal desconectada: %s", installation_id)


@router.websocket("/ws/live")
async def ws_dashboard_live(
    websocket: WebSocket,
    token: Annotated[Optional[str], Query()] = None,
) -> None:
    jwt_token = token or websocket.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not jwt_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        payload = decode_token(jwt_token)
        if not payload.get("sub"):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await live_hub.register_dashboard(websocket)
    try:
        snap = await live_hub.snapshot_for_dashboard()
        await websocket.send_json(snap)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await live_hub.unregister_dashboard(websocket)
