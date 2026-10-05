"""WebSocket estado panel para dashboard local."""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.services import panel_jwt
from app.services import panel_live_hub

log = logging.getLogger("panel.ws")
router = APIRouter()


@router.websocket("/ws/live")
async def ws_panel_live(
    websocket: WebSocket,
    token: Annotated[Optional[str], Query()] = None,
) -> None:
    jwt_token = token or websocket.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not jwt_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        panel_jwt.decode_access_token_username(jwt_token)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await panel_live_hub.register(websocket)
    try:
        from app.api.routes.panel import _build_status_payload

        payload = await asyncio.to_thread(_build_status_payload)
        await websocket.send_json({"type": "panel_status", "payload": payload})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await panel_live_hub.unregister(websocket)
