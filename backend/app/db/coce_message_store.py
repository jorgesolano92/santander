"""Mensajes COCE recibidos en la sucursal (historial tablet/panel)."""
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
            payload_json TEXT,
            seen_at TEXT
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(coce_messages)").fetchall()}
    if "seen_at" not in cols:
        conn.execute("ALTER TABLE coce_messages ADD COLUMN seen_at TEXT")
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
        INSERT INTO coce_messages (id, title, body, urgent, received_at, payload_json, seen_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
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
    row = conn.execute(
        "SELECT id, title, body, urgent, received_at, seen_at FROM coce_messages WHERE id = ?",
        (message_id,),
    ).fetchone()
    conn.close()
    return {
        "id": row[0],
        "title": row[1],
        "body": row[2],
        "urgent": bool(row[3]),
        "received_at": row[4],
        "seen_at": row[5],
    }


def mark_seen(
    message_ids: list[str],
    *,
    seen_at: Optional[str] = None,
) -> list[str]:
    """Marca mensajes como leídos localmente. Devuelve ids recién marcados."""
    _init_db()
    ids = [str(i).strip() for i in message_ids if str(i).strip()]
    if not ids:
        return []
    ts = (seen_at or "").strip() or _now()
    newly: list[str] = []
    conn = get_connection()
    for mid in ids:
        row = conn.execute(
            "SELECT seen_at FROM coce_messages WHERE id = ?",
            (mid,),
        ).fetchone()
        if not row:
            continue
        if row[0]:
            continue
        conn.execute(
            "UPDATE coce_messages SET seen_at = ? WHERE id = ? AND seen_at IS NULL",
            (ts, mid),
        )
        newly.append(mid)
    conn.commit()
    conn.close()
    return newly


def list_messages(*, limit: int = 100) -> list[dict[str, Any]]:
    _init_db()
    limit = max(1, min(int(limit), _MAX_MESSAGES))
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, title, body, urgent, received_at, seen_at
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
            "seen_at": row[5],
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
