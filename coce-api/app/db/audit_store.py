from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.schema import ensure_schema
from app.db.session import get_connection


def record_audit(
    *,
    actor_username: str,
    action: str,
    success: bool = True,
    branch_id: Optional[str] = None,
    branch_nombre: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> int:
    ensure_schema()
    now = datetime.now(timezone.utc).isoformat()
    detail_s = json.dumps(detail, ensure_ascii=False) if detail else None
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO audit_logs (
                created_at, actor_username, action, branch_id, branch_nombre,
                success, detail, ip_address
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                actor_username,
                action,
                branch_id,
                branch_nombre,
                1 if success else 0,
                detail_s,
                ip_address,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_audit(
    *,
    limit: int = 200,
    offset: int = 0,
    branch_id: Optional[str] = None,
    action: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
) -> list[dict[str, Any]]:
    ensure_schema()
    clauses: list[str] = []
    params: list[Any] = []
    if branch_id:
        clauses.append("branch_id = ?")
        params.append(branch_id)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if from_ts:
        clauses.append("created_at >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("created_at <= ?")
        params.append(to_ts)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    sql = f"""
        SELECT id, created_at, actor_username, action, branch_id, branch_nombre,
               success, detail, ip_address
        FROM audit_logs
        {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        detail = None
        if r["detail"]:
            try:
                detail = json.loads(r["detail"])
            except json.JSONDecodeError:
                detail = {"raw": r["detail"]}
        out.append(
            {
                "id": r["id"],
                "createdAt": r["created_at"],
                "actorUsername": r["actor_username"],
                "action": r["action"],
                "branchId": r["branch_id"],
                "branchNombre": r["branch_nombre"],
                "success": bool(r["success"]),
                "detail": detail,
                "ipAddress": r["ip_address"],
            }
        )
    return out
