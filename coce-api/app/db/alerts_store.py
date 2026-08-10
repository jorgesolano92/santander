"""Historial corto de alertas de sucursal (incendio / emergencia / puerta)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.schema import ensure_schema
from app.db.session import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_alert_event(
    *,
    branch_id: str,
    branch_nombre: str,
    alert_type: str,
    active: bool,
    message: str = "",
    detail: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    ensure_schema()
    now = _now()
    with get_connection() as conn:
        if active:
            alert_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO coce_alerts (
                    id, created_at, resolved_at, branch_id, branch_nombre,
                    alert_type, active, message, detail_json
                ) VALUES (?, ?, NULL, ?, ?, ?, 1, ?, ?)
                """,
                (
                    alert_id,
                    now,
                    branch_id,
                    branch_nombre,
                    alert_type,
                    message or "",
                    str(detail or {}),
                ),
            )
            conn.commit()
            return get_alert(alert_id) or {}

        # Resolver la alerta activa más reciente del mismo tipo/sucursal
        row = conn.execute(
            """
            SELECT id FROM coce_alerts
            WHERE branch_id = ? AND alert_type = ? AND active = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (branch_id, alert_type),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE coce_alerts
                SET active = 0, resolved_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            conn.commit()
            return get_alert(row["id"]) or {}
        return {}


def get_alert(alert_id: str) -> Optional[dict[str, Any]]:
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM coce_alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_alerts(
    *,
    limit: int = 100,
    active: Optional[bool] = None,
    branch_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    ensure_schema()
    clauses: list[str] = []
    params: list[Any] = []
    if active is not None:
        clauses.append("active = ?")
        params.append(1 if active else 0)
    if branch_id:
        clauses.append("branch_id = ?")
        params.append(branch_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM coce_alerts
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "resolvedAt": row["resolved_at"],
        "branchId": row["branch_id"],
        "branchNombre": row["branch_nombre"],
        "alertType": row["alert_type"],
        "active": bool(row["active"]),
        "message": row["message"] or "",
        "detail": row["detail_json"] or "",
    }
