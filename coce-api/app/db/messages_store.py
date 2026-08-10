from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.schema import ensure_schema
from app.db.session import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_message(
    *,
    actor_username: str,
    title: str,
    body: str,
    urgent: bool,
    branch_id: str,
    branch_nombre: str,
    delivery_status: str,
) -> dict[str, Any]:
    ensure_schema()
    message_id = str(uuid.uuid4())
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO coce_messages (
                id, created_at, actor_username, title, body, urgent,
                branch_id, branch_nombre, delivery_status, delivered_at,
                read_at, read_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                message_id,
                now,
                actor_username,
                title.strip(),
                body.strip(),
                1 if urgent else 0,
                branch_id,
                branch_nombre,
                delivery_status,
                now if delivery_status == "delivered" else None,
            ),
        )
        conn.commit()
    return get_message(message_id) or {}


def update_delivery(message_id: str, delivery_status: str) -> None:
    ensure_schema()
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE coce_messages
            SET delivery_status = ?, delivered_at = COALESCE(?, delivered_at)
            WHERE id = ?
            """,
            (
                delivery_status,
                now if delivery_status == "delivered" else None,
                message_id,
            ),
        )
        conn.commit()


def mark_read(
    message_id: str,
    *,
    read_by: str,
    read_at: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Marca lectura (idempotente: no sobrescribe read_at previo)."""
    ensure_schema()
    now = (read_at or "").strip() or _now()
    channel = (read_by or "").strip() or "unknown"
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, read_at FROM coce_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if not row:
            return None
        if row["read_at"]:
            # Ya leído: enriquecer read_by si llega otro canal
            prev_by = ""
            cur = conn.execute(
                "SELECT read_by FROM coce_messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if cur and cur["read_by"]:
                prev_by = str(cur["read_by"])
            if channel and channel not in prev_by.split(","):
                merged = f"{prev_by},{channel}" if prev_by else channel
                conn.execute(
                    "UPDATE coce_messages SET read_by = ? WHERE id = ?",
                    (merged, message_id),
                )
                conn.commit()
            return get_message(message_id)
        conn.execute(
            """
            UPDATE coce_messages
            SET read_at = ?,
                read_by = ?,
                delivery_status = CASE
                    WHEN delivery_status IN ('pending', 'offline') THEN delivery_status
                    ELSE 'delivered'
                END
            WHERE id = ?
            """,
            (now, channel, message_id),
        )
        conn.commit()
    return get_message(message_id)


def delete_message(message_id: str) -> bool:
    ensure_schema()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM coce_messages WHERE id = ?", (message_id,))
        conn.commit()
        return cur.rowcount > 0


def get_message(message_id: str) -> Optional[dict[str, Any]]:
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM coce_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_messages(
    *,
    limit: int = 100,
    offset: int = 0,
    branch_id: Optional[str] = None,
    urgent: Optional[bool] = None,
    delivery_status: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    q: Optional[str] = None,
    read: Optional[bool] = None,
) -> list[dict[str, Any]]:
    ensure_schema()
    clauses: list[str] = []
    params: list[Any] = []
    if branch_id:
        clauses.append("branch_id = ?")
        params.append(branch_id)
    if urgent is not None:
        clauses.append("urgent = ?")
        params.append(1 if urgent else 0)
    if delivery_status == "read":
        clauses.append("read_at IS NOT NULL")
    elif delivery_status:
        clauses.append("delivery_status = ?")
        params.append(delivery_status)
        if delivery_status == "delivered":
            clauses.append("read_at IS NULL")
    if read is True:
        clauses.append("read_at IS NOT NULL")
    elif read is False:
        clauses.append("read_at IS NULL")
    if from_ts:
        clauses.append("created_at >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("created_at <= ?")
        params.append(to_ts)
    if q:
        clauses.append("(title LIKE ? OR body LIKE ? OR branch_nombre LIKE ?)")
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM coce_messages
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "actorUsername": row["actor_username"],
        "title": row["title"],
        "body": row["body"],
        "urgent": bool(row["urgent"]),
        "branchId": row["branch_id"],
        "branchNombre": row["branch_nombre"],
        "deliveryStatus": row["delivery_status"],
        "deliveredAt": row["delivered_at"],
        "readAt": row["read_at"] if "read_at" in row.keys() else None,
        "readBy": row["read_by"] if "read_by" in row.keys() else None,
    }
