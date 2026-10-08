"""WebSocket llamadas entrantes para tablets."""
from __future__ import annotations

import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.db import authorized_tablets_store as ats
from app.services import tablet_call_hub
from app.services import tablet_jwt

log = logging.getLogger("tablet.ws")
router = APIRouter()


@router.websocket("/ws/calls")
async def ws_tablet_calls(
    websocket: WebSocket,
    token: Annotated[Optional[str], Query()] = None,
    device_id: Annotated[Optional[str], Query(max_length=128)] = None,
) -> None:
    jwt_token = token or websocket.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not jwt_token:
        log.warning("Tablet WS rechazado: falta token (cliente=%s)", websocket.client)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        username = tablet_jwt.decode_access_token_username(jwt_token)
    except ValueError as e:
        # Cerrar sin accept() → uvicorn registra "403 Forbidden" en el handshake.
        log.warning(
            "Tablet WS rechazado: JWT inválido/caducado (%s) cliente=%s",
            e,
            websocket.client,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    client_ip = websocket.client.host if websocket.client else None
    android_id = (device_id or "").strip().lower() or None
    tablet: Optional[dict] = None
    if android_id:
        auth = ats.check_authorization(android_id, client_ip)
        if not auth.get("authorized"):
            log.warning(
                "Tablet WS rechazado: %s no autorizada (%s)", android_id, auth.get("reason")
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        tablet = ats.get_by_android_id(android_id)

    await websocket.accept()
    client_id = uuid.uuid4().hex
    await tablet_call_hub.register(
        client_id, websocket, username, ip=client_ip, android_id=android_id
    )
    await websocket.send_json(
        {
            "type": "registered",
            "client_id": client_id,
            "username": username,
            "tablet_number": (tablet or {}).get("number"),
            "tablet_name": (tablet or {}).get("name"),
        }
    )

    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict):
                await tablet_call_hub.handle_client_message(client_id, data)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.debug("Tablet WS error id=%s: %s", client_id, e)
    finally:
        await tablet_call_hub.unregister(client_id)
