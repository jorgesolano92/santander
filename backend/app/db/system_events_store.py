"""Eventos del sistema e histórico en SQLite (retención configurable)."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.db.session import get_connection
from app.request_context import get_actor


def default_event_source() -> str:
    p, _ = get_actor()
    if p == "panel":
        return "panel_ui"
    if p == "tablet":
        return "tablet_api"
    return "system"


def ensure_system_events_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'general',
                source TEXT NOT NULL DEFAULT 'system',
                actor_principal TEXT NOT NULL DEFAULT 'system',
                actor_username TEXT,
                board_id INTEGER NOT NULL DEFAULT 0,
                payload TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_system_events_created ON system_events(created_at DESC)"
        )
        conn.commit()


def purge_events_older_than(days: Optional[int] = None) -> int:
    """Elimina eventos con created_at anterior al cutoff. Devuelve filas borradas."""
    ensure_system_events_schema()
    d = days if days is not None else settings.events_retention_days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, d))).isoformat()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM system_events WHERE created_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount


def record_event(
    severity: str,
    message: str,
    *,
    board_id: int = 0,
    event_type: str = "general",
    source: Optional[str] = None,
    actor_principal: Optional[str] = None,
    actor_username: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Inserta un evento. Si actor_* es None, usa el contexto de petición (panel/tablet) o system.
    """
    ensure_system_events_schema()
    ctx_p, ctx_u = get_actor()
    ap = actor_principal if actor_principal is not None else ctx_p
    au = actor_username if actor_username is not None else ctx_u
    if ap not in ("panel", "tablet", "system"):
        ap = "system"
    src = source if source is not None else default_event_source()
    now = datetime.now(timezone.utc).isoformat()
    payload_s = json.dumps(payload, ensure_ascii=False) if payload is not None else None
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO system_events (
                created_at, severity, message, event_type, source,
                actor_principal, actor_username, board_id, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                severity.upper()[:16],
                message,
                event_type,
                src,
                ap,
                au,
                board_id,
                payload_s,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _row_to_api_dict(row: Tuple[Any, ...]) -> Dict[str, Any]:
    _id, created_at, severity, message, event_type, source, actor_principal, actor_username, board_id, payload = row
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except Exception:  # noqa: BLE001
        ts = str(created_at)[:8] if created_at else ""
    out: Dict[str, Any] = {
        "id": int(_id),
        "ts": ts,
        "date": str(created_at),
        "type": str(severity),
        "msg": str(message),
        "board": int(board_id) if board_id is not None else 0,
        "event_type": str(event_type),
        "source": str(source),
        "actor_principal": str(actor_principal),
        "actor_username": actor_username,
    }
    if payload:
        try:
            out["payload"] = json.loads(payload)
        except Exception:  # noqa: BLE001
            out["payload_raw"] = str(payload)
    return out


def list_events(
    *,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    severity_filter: Optional[str] = None,
    event_type_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[int, List[Dict[str, Any]]]:
    ensure_system_events_schema()
    where: List[str] = ["1=1"]
    params: List[Any] = []
    if from_date:
        where.append("created_at >= ?")
        params.append(from_date)
    if to_date:
        where.append("created_at <= ?")
        params.append(to_date)
    if severity_filter:
        where.append("UPPER(severity) = ?")
        params.append(severity_filter.upper())
    if event_type_filter:
        where.append("event_type = ?")
        params.append(event_type_filter)
    wh = " AND ".join(where)
    with get_connection() as conn:
        total_row = conn.execute(f"SELECT COUNT(*) FROM system_events WHERE {wh}", params).fetchone()
        total = int(total_row[0]) if total_row else 0
        params2 = list(params)
        params2.extend([limit, offset])
        rows = conn.execute(
            f"""
            SELECT id, created_at, severity, message, event_type, source,
                   actor_principal, actor_username, board_id, payload
            FROM system_events
            WHERE {wh}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            params2,
        ).fetchall()
    return total, [_row_to_api_dict(tuple(r)) for r in rows]


def clear_all_events() -> int:
    ensure_system_events_schema()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM system_events")
        conn.commit()
        return cur.rowcount


def export_csv(
    *,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    severity_filter: Optional[str] = None,
    event_type_filter: Optional[str] = None,
    limit: int = 50_000,
) -> str:
    total, events = list_events(
        from_date=from_date,
        to_date=to_date,
        severity_filter=severity_filter,
        event_type_filter=event_type_filter,
        limit=limit,
        offset=0,
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "created_at",
            "severity",
            "event_type",
            "message",
            "source",
            "actor_principal",
            "actor_username",
            "board_id",
        ]
    )
    for e in events:
        w.writerow(
            [
                e["id"],
                e["date"],
                e["type"],
                e["event_type"],
                e["msg"],
                e["source"],
                e["actor_principal"],
                e.get("actor_username") or "",
                e["board"],
            ]
        )
    _ = total
    return buf.getvalue()
