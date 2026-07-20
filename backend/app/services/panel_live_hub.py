"""Fan-out en vivo del estado panel al dashboard local (WebSocket)."""
from __future__ import annotations

import asyncio
import logging
import queue
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("panel.live")

_clients: set[WebSocket] = set()
_pending: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=300)


async def register(ws: WebSocket) -> None:
    _clients.add(ws)
    log.info("Panel WS cliente conectado (total=%s)", len(_clients))


async def unregister(ws: WebSocket) -> None:
    _clients.discard(ws)
    log.info("Panel WS cliente desconectado (total=%s)", len(_clients))


async def broadcast(message: dict[str, Any]) -> None:
    if not _clients:
        log.debug("Panel WS broadcast omitido: sin clientes")
        return
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_json(message)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


def publish_sync(message: dict[str, Any]) -> None:
    """Cola thread-safe; el pump asyncio vacía hacia los clientes WS."""
    try:
        _pending.put_nowait(message)
    except queue.Full:
        log.warning("Panel WS cola llena, evento descartado")


async def pump_loop() -> None:
    while True:
        await asyncio.sleep(0.05)
        batch: list[dict[str, Any]] = []
        for _ in range(50):
            try:
                batch.append(_pending.get_nowait())
            except queue.Empty:
                break
        for msg in batch:
            await broadcast(msg)


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
