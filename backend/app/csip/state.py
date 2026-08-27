"""Estado en memoria: últimas notificaciones recibidas de la placa CSIP."""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_MAX = 50
_lock = threading.Lock()
_recent: deque[dict[str, Any]] = deque(maxlen=_MAX)


def record_notification(canal: str, body: dict[str, Any], *, forwarded: bool) -> dict[str, Any]:
    entry = {
        "canal": canal,
        "body": body,
        "forwarded_to_zaguan": forwarded,
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ts": time.time(),
    }
    with _lock:
        _recent.appendleft(entry)
    return entry


def list_recent(limit: int = 20) -> list[dict[str, Any]]:
    n = max(1, min(int(limit), _MAX))
    with _lock:
        return list(_recent)[:n]


def clear_recent() -> None:
    with _lock:
        _recent.clear()
