"""Tablets autorizadas por Android ID (allowlist del panel)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.db.session import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS authorized_tablets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                android_id TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS authorized_tablets_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enforcement_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT id FROM authorized_tablets_settings WHERE id = 1"
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO authorized_tablets_settings (id, enforcement_enabled, updated_at)
                VALUES (1, 0, ?)
                """,
                (_now(),),
            )
        conn.commit()


def _normalize_android_id(android_id: str) -> str:
    return str(android_id or "").strip().lower()


def get_settings() -> dict[str, Any]:
    _init()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT enforcement_enabled, updated_at FROM authorized_tablets_settings WHERE id = 1"
        ).fetchone()
    if not row:
        return {"enforcement_enabled": False, "updated_at": None}
    return {
        "enforcement_enabled": bool(int(row[0])),
        "updated_at": row[1],
    }


def set_enforcement_enabled(enabled: bool) -> dict[str, Any]:
    _init()
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE authorized_tablets_settings
            SET enforcement_enabled = ?, updated_at = ?
            WHERE id = 1
            """,
            (1 if enabled else 0, now),
        )
        conn.commit()
    return get_settings()


def list_tablets() -> list[dict[str, Any]]:
    _init()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, android_id, label, enabled, created_at, updated_at, last_seen_at
            FROM authorized_tablets
            ORDER BY label COLLATE NOCASE, android_id
            """
        ).fetchall()
    return [
        {
            "id": int(r[0]),
            "android_id": r[1],
            "label": r[2] or "",
            "enabled": bool(int(r[3])),
            "created_at": r[4],
            "updated_at": r[5],
            "last_seen_at": r[6],
        }
        for r in rows
    ]


def get_by_android_id(android_id: str) -> Optional[dict[str, Any]]:
    aid = _normalize_android_id(android_id)
    if not aid:
        return None
    _init()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, android_id, label, enabled, created_at, updated_at, last_seen_at
            FROM authorized_tablets
            WHERE android_id = ?
            """,
            (aid,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "android_id": row[1],
        "label": row[2] or "",
        "enabled": bool(int(row[3])),
        "created_at": row[4],
        "updated_at": row[5],
        "last_seen_at": row[6],
    }


def add_tablet(android_id: str, label: str = "") -> dict[str, Any]:
    aid = _normalize_android_id(android_id)
    if not aid:
        raise ValueError("android_id vacío")
    if len(aid) > 128:
        raise ValueError("android_id demasiado largo")
    now = _now()
    _init()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM authorized_tablets WHERE android_id = ?",
            (aid,),
        ).fetchone()
        if existing:
            raise ValueError("Ese Android ID ya está registrado")
        cur = conn.execute(
            """
            INSERT INTO authorized_tablets (android_id, label, enabled, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (aid, (label or "").strip()[:120], now, now),
        )
        conn.commit()
        tid = int(cur.lastrowid)
    row = get_by_android_id(aid)
    assert row is not None
    row["id"] = tid
    return row


def update_tablet(
    tablet_id: int,
    *,
    label: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    _init()
    now = _now()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, label, enabled FROM authorized_tablets WHERE id = ?",
            (int(tablet_id),),
        ).fetchone()
        if not row:
            return None
        new_label = row[1] if label is None else str(label).strip()[:120]
        new_enabled = int(row[2]) if enabled is None else (1 if enabled else 0)
        conn.execute(
            """
            UPDATE authorized_tablets
            SET label = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_label, new_enabled, now, int(tablet_id)),
        )
        conn.commit()
    with get_connection() as conn:
        r = conn.execute(
            """
            SELECT id, android_id, label, enabled, created_at, updated_at, last_seen_at
            FROM authorized_tablets WHERE id = ?
            """,
            (int(tablet_id),),
        ).fetchone()
    if not r:
        return None
    return {
        "id": int(r[0]),
        "android_id": r[1],
        "label": r[2] or "",
        "enabled": bool(int(r[3])),
        "created_at": r[4],
        "updated_at": r[5],
        "last_seen_at": r[6],
    }


def delete_tablet(tablet_id: int) -> bool:
    _init()
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM authorized_tablets WHERE id = ?",
            (int(tablet_id),),
        )
        conn.commit()
        return cur.rowcount > 0


def touch_last_seen(android_id: str) -> None:
    aid = _normalize_android_id(android_id)
    if not aid:
        return
    _init()
    with get_connection() as conn:
        conn.execute(
            "UPDATE authorized_tablets SET last_seen_at = ? WHERE android_id = ?",
            (_now(), aid),
        )
        conn.commit()


def check_authorization(android_id: str) -> dict[str, Any]:
    """
    Comprueba si una tablet puede usarse.
    Si enforcement_enabled=false → autorizada siempre.
    Si no → debe existir en allowlist y enabled=true.
    """
    aid = _normalize_android_id(android_id)
    settings = get_settings()
    enforcement = bool(settings.get("enforcement_enabled", False))
    if not aid:
        return {
            "authorized": False,
            "enforcement_enabled": enforcement,
            "android_id": "",
            "reason": "android_id_missing",
            "label": None,
        }
    if not enforcement:
        touch_last_seen(aid)
        row = get_by_android_id(aid)
        return {
            "authorized": True,
            "enforcement_enabled": False,
            "android_id": aid,
            "reason": "enforcement_disabled",
            "label": (row or {}).get("label"),
        }
    row = get_by_android_id(aid)
    if not row:
        return {
            "authorized": False,
            "enforcement_enabled": True,
            "android_id": aid,
            "reason": "not_registered",
            "label": None,
        }
    if not row.get("enabled"):
        return {
            "authorized": False,
            "enforcement_enabled": True,
            "android_id": aid,
            "reason": "disabled",
            "label": row.get("label"),
        }
    touch_last_seen(aid)
    return {
        "authorized": True,
        "enforcement_enabled": True,
        "android_id": aid,
        "reason": "ok",
        "label": row.get("label"),
    }
