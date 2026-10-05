"""Cliente WebSocket saliente hacia coce-api."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import websockets
from websockets.exceptions import ConnectionClosed

from app.coce.dispatcher import handle_coce_message
from app.coce.notify import coce_enabled, drain_outbound, emit_coce_event
from app.coce.state import build_heartbeat_payload
from app.core.config import settings

log = logging.getLogger("coce.client")
_send_lock: asyncio.Lock | None = None


def _ws_url_with_token() -> str:
    base = (settings.coce_ws_url or "").strip()
    if not base:
        return ""
    parsed = urlparse(base)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if settings.coce_ingest_token:
        q["token"] = settings.coce_ingest_token
    new_query = urlencode(q)
    return urlunparse(parsed._replace(query=new_query))


async def _send_json(ws: Any, data: dict[str, Any]) -> None:
    global _send_lock
    if _send_lock is None:
        _send_lock = asyncio.Lock()
    async with _send_lock:
        await ws.send(json.dumps(data))


async def _heartbeat_loop(ws: Any) -> None:
    interval = max(15, int(settings.coce_heartbeat_interval_seconds))
    while True:
        await asyncio.sleep(interval)
        payload = await asyncio.to_thread(build_heartbeat_payload)
        await _send_json(ws, {"type": "heartbeat", "payload": payload})


async def _outbound_loop(ws: Any) -> None:
    while True:
        await asyncio.sleep(0.25)
        batch = await asyncio.to_thread(drain_outbound, 50)
        for msg in batch:
            await _send_json(ws, msg)


async def _recv_loop(ws: Any) -> None:
    async for raw in ws:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            await handle_coce_message(data)


async def coce_ws_client_loop() -> None:
    if not coce_enabled():
        log.info("COCE WS desactivado (falta URL, installation_id o coce_ws_enabled=false)")
        return
    url = _ws_url_with_token()
    reconnect = max(3, int(settings.coce_reconnect_seconds))
    while True:
        try:
            log.info("Conectando COCE WS: %s", settings.coce_ws_url)
            extra_headers: list[tuple[str, str]] = []
            if settings.coce_ingest_token:
                extra_headers.append(("X-Coce-Ingest-Token", settings.coce_ingest_token))
            async with websockets.connect(
                url,
                additional_headers=extra_headers,
                ping_interval=30,
                ping_timeout=20,
            ) as ws:
                log.info("COCE WS conectado")
                payload = await asyncio.to_thread(build_heartbeat_payload)
                await _send_json(ws, {"type": "heartbeat", "payload": payload})
                await asyncio.gather(
                    _heartbeat_loop(ws),
                    _outbound_loop(ws),
                    _recv_loop(ws),
                )
        except ConnectionClosed as e:
            log.warning("COCE WS cerrado: %s", e)
        except Exception as e:  # noqa: BLE001
            log.warning("COCE WS error: %s", e)
        await asyncio.sleep(reconnect)


def start_coce_client_task() -> asyncio.Task | None:
    if not coce_enabled():
        return None
    return asyncio.create_task(coce_ws_client_loop())
