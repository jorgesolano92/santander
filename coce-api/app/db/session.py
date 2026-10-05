"""Conexión SQLite para COCE central."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from app.core.config import settings


def _db_path() -> Path:
    url = settings.database_url
    if url.startswith("sqlite:///"):
        raw = url.replace("sqlite:///", "", 1)
        p = Path(raw)
        if not p.is_absolute():
            p = Path(__file__).resolve().parent.parent.parent / raw
        return p
    raise ValueError(f"database_url no soportada: {url}")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
