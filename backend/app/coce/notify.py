"""Cola thread-safe de eventos hacia el cliente WebSocket COCE."""
from __future__ import annotations

import queue
import time
from typing import Any

from app.core.config import settings

_outbound: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=500)


def coce_enabled() -> bool:
    return bool(
        settings.coce_ws_enabled
        and settings.coce_ws_url
        and settings.coce_installation_id
    )


def emit_coce_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    if not coce_enabled():
        return
    msg = {
        "type": event_type,
        "payload": payload or {},
        "ts": time.time(),
    }
    try:
        _outbound.put_nowait(msg)
    except queue.Full:
        pass


def drain_outbound(max_items: int = 50) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for _ in range(max_items):
        try:
            items.append(_outbound.get_nowait())
        except queue.Empty:
            break
    return items
