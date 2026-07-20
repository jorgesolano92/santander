"""Mensajes COCE recibidos en la sucursal (historial tablet)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.session import get_connection

_MAX_MESSAGES = 200


def _init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS coce_messages (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            urgent INTEGER NOT NULL DEFAULT 0,
            received_at TEXT NOT NULL,
            payload_json TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_coce_messages_received ON coce_messages(received_at DESC)"
    )
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_message(
    *,
    message_id: str,
    title: str,
    body: str,
    urgent: bool,
    sent_at: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    _init_db()
    received_at = sent_at or _now()
    payload_json = json.dumps(extra or {}, ensure_ascii=False)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO coce_messages (id, title, body, urgent, received_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            body = excluded.body,
            urgent = excluded.urgent,
            received_at = excluded.received_at,
            payload_json = excluded.payload_json
        """,
        (message_id, title.strip(), body.strip(), 1 if urgent else 0, received_at, payload_json),
    )
    conn.commit()
    _trim_old(conn)
    conn.close()
    return {
        "id": message_id,
        "title": title.strip(),
        "body": body.strip(),
        "urgent": bool(urgent),
        "received_at": received_at,
    }


def list_messages(*, limit: int = 100) -> list[dict[str, Any]]:
    _init_db()
    limit = max(1, min(int(limit), _MAX_MESSAGES))
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, title, body, urgent, received_at
        FROM coce_messages
        ORDER BY received_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "title": row[1],
            "body": row[2],
            "urgent": bool(row[3]),
            "received_at": row[4],
        }
        for row in rows
    ]


def _trim_old(conn) -> None:
    conn.execute(
        """
        DELETE FROM coce_messages
        WHERE id NOT IN (
            SELECT id FROM coce_messages ORDER BY received_at DESC LIMIT ?
        )
        """,
        (_MAX_MESSAGES,),
    )
    conn.commit()
