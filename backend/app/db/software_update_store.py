"""Estado local de actualizaciones recibidas desde COCE."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.session import get_connection


def _init() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS software_update_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            pending_json TEXT,
            last_apk_version TEXT,
            last_apk_published_at TEXT,
            last_panel_version TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_state() -> dict[str, Any]:
    _init()
    conn = get_connection()
    row = conn.execute(
        "SELECT pending_json, last_apk_version, last_apk_published_at, last_panel_version, updated_at FROM software_update_state WHERE id=1"
    ).fetchone()
    conn.close()
    if not row:
        return {
            "pending": None,
            "last_apk_version": None,
            "last_apk_published_at": None,
            "last_panel_version": None,
            "updated_at": None,
        }
    pending = None
    if row[0]:
        try:
            pending = json.loads(row[0])
        except json.JSONDecodeError:
            pending = None
    return {
        "pending": pending,
        "last_apk_version": row[1],
        "last_apk_published_at": row[2],
        "last_panel_version": row[3],
        "updated_at": row[4],
    }


def set_pending(payload: dict[str, Any]) -> dict[str, Any]:
    _init()
    now = _now()
    raw = json.dumps(payload, ensure_ascii=False)
    conn = get_connection()
    exists = conn.execute("SELECT id FROM software_update_state WHERE id=1").fetchone()
    if exists:
        conn.execute(
            "UPDATE software_update_state SET pending_json=?, updated_at=? WHERE id=1",
            (raw, now),
        )
    else:
        conn.execute(
            """
            INSERT INTO software_update_state (id, pending_json, updated_at)
            VALUES (1, ?, ?)
            """,
            (raw, now),
        )
    conn.commit()
    conn.close()
    return get_state()


def clear_pending() -> None:
    _init()
    conn = get_connection()
    conn.execute(
        "UPDATE software_update_state SET pending_json=NULL, updated_at=? WHERE id=1",
        (_now(),),
    )
    conn.commit()
    conn.close()


def mark_apk_seen(version: str, published_at: Optional[str] = None) -> None:
    _init()
    now = _now()
    conn = get_connection()
    exists = conn.execute("SELECT id FROM software_update_state WHERE id=1").fetchone()
    if exists:
        conn.execute(
            """
            UPDATE software_update_state
            SET last_apk_version=?, last_apk_published_at=?, pending_json=NULL, updated_at=?
            WHERE id=1
            """,
            (version, published_at, now),
        )
    else:
        conn.execute(
            """
            INSERT INTO software_update_state
            (id, last_apk_version, last_apk_published_at, pending_json, updated_at)
            VALUES (1, ?, ?, NULL, ?)
            """,
            (version, published_at, now),
        )
    conn.commit()
    conn.close()


def mark_panel_applied(version: str) -> None:
    _init()
    now = _now()
    conn = get_connection()
    exists = conn.execute("SELECT id FROM software_update_state WHERE id=1").fetchone()
    if exists:
        conn.execute(
            """
            UPDATE software_update_state
            SET last_panel_version=?, pending_json=NULL, updated_at=?
            WHERE id=1
            """,
            (version, now),
        )
    else:
        conn.execute(
            """
            INSERT INTO software_update_state (id, last_panel_version, pending_json, updated_at)
            VALUES (1, ?, NULL, ?)
            """,
            (version, now),
        )
    conn.commit()
    conn.close()
