"""Tablets de la sucursal por Android ID: allowlist, numeración «Tablet N» y config propia."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.session import get_connection

MAX_TABLETS = 32

_initialized = False

_COLS = (
    "id, android_id, label, enabled, created_at, updated_at, last_seen_at, "
    "tablet_number, config_json IS NOT NULL, config_updated_at, last_ip, pending"
)

_EXTRA_COLUMNS = (
    ("tablet_number", "INTEGER"),
    ("config_json", "TEXT"),
    ("config_revision", "TEXT"),
    ("config_updated_at", "TEXT"),
    ("last_ip", "TEXT"),
    ("pending", "INTEGER NOT NULL DEFAULT 0"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_free_number(conn) -> int:
    used = {
        int(r[0])
        for r in conn.execute(
            "SELECT tablet_number FROM authorized_tablets WHERE tablet_number IS NOT NULL"
        ).fetchall()
    }
    n = 1
    while n in used:
        n += 1
    return n


def _migrate(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(authorized_tablets)").fetchall()}
    for name, ddl in _EXTRA_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE authorized_tablets ADD COLUMN {name} {ddl}")
    rows = conn.execute(
        "SELECT id FROM authorized_tablets WHERE tablet_number IS NULL ORDER BY id"
    ).fetchall()
    for (tid,) in rows:
        conn.execute(
            "UPDATE authorized_tablets SET tablet_number = ? WHERE id = ?",
            (_next_free_number(conn), int(tid)),
        )


def _init() -> None:
    global _initialized
    if _initialized:
        return
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
        _migrate(conn)
        conn.commit()
    _initialized = True


def _normalize_android_id(android_id: str) -> str:
    return str(android_id or "").strip().lower()


def tablet_display_name(number: Optional[int]) -> str:
    return f"Tablet {number}" if number else "Tablet"


def _row_to_dict(r: tuple) -> dict[str, Any]:
    number = int(r[7]) if r[7] is not None else None
    return {
        "id": int(r[0]),
        "android_id": r[1],
        "label": r[2] or "",
        "enabled": bool(int(r[3])),
        "created_at": r[4],
        "updated_at": r[5],
        "last_seen_at": r[6],
        "number": number,
        "name": tablet_display_name(number),
        "has_own_config": bool(r[8]),
        "config_updated_at": r[9],
        "last_ip": r[10],
        "pending": bool(int(r[11] or 0)),
    }


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
            f"SELECT {_COLS} FROM authorized_tablets ORDER BY tablet_number, id"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(tablet_id: int) -> Optional[dict[str, Any]]:
    _init()
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM authorized_tablets WHERE id = ?",
            (int(tablet_id),),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_android_id(android_id: str) -> Optional[dict[str, Any]]:
    aid = _normalize_android_id(android_id)
    if not aid:
        return None
    _init()
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM authorized_tablets WHERE android_id = ?",
            (aid,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def add_tablet(
    android_id: str,
    label: str = "",
    *,
    enabled: bool = True,
    pending: bool = False,
) -> dict[str, Any]:
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
        total = conn.execute("SELECT COUNT(*) FROM authorized_tablets").fetchone()[0]
        if int(total) >= MAX_TABLETS:
            raise ValueError(f"Máximo {MAX_TABLETS} tablets por sucursal")
        conn.execute(
            """
            INSERT INTO authorized_tablets
                (android_id, label, enabled, created_at, updated_at, tablet_number, pending)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                (label or "").strip()[:120],
                1 if enabled else 0,
                now,
                now,
                _next_free_number(conn),
                1 if pending else 0,
            ),
        )
        conn.commit()
    row = get_by_android_id(aid)
    assert row is not None
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
            "SELECT id, label, enabled, pending FROM authorized_tablets WHERE id = ?",
            (int(tablet_id),),
        ).fetchone()
        if not row:
            return None
        new_label = row[1] if label is None else str(label).strip()[:120]
        new_enabled = int(row[2]) if enabled is None else (1 if enabled else 0)
        new_pending = 0 if enabled is not None else int(row[3] or 0)
        conn.execute(
            """
            UPDATE authorized_tablets
            SET label = ?, enabled = ?, pending = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_label, new_enabled, new_pending, now, int(tablet_id)),
        )
        conn.commit()
    return get_by_id(tablet_id)


def delete_tablet(tablet_id: int) -> bool:
    _init()
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM authorized_tablets WHERE id = ?",
            (int(tablet_id),),
        )
        conn.commit()
        return cur.rowcount > 0


def touch_last_seen(android_id: str, ip: Optional[str] = None) -> None:
    aid = _normalize_android_id(android_id)
    if not aid:
        return
    _init()
    with get_connection() as conn:
        if ip:
            conn.execute(
                "UPDATE authorized_tablets SET last_seen_at = ?, last_ip = ? WHERE android_id = ?",
                (_now(), str(ip)[:64], aid),
            )
        else:
            conn.execute(
                "UPDATE authorized_tablets SET last_seen_at = ? WHERE android_id = ?",
                (_now(), aid),
            )
        conn.commit()


def ensure_registered(android_id: str, ip: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    Devuelve la ficha de la tablet, dándola de alta como «Tablet N» si es nueva.
    Con autorización exigida, el alta queda desactivada y pendiente de aprobar en el panel.
    """
    aid = _normalize_android_id(android_id)
    if not aid or len(aid) > 128:
        return None
    if get_by_android_id(aid) is None:
        enforcement = bool(get_settings().get("enforcement_enabled", False))
        try:
            add_tablet(aid, "", enabled=not enforcement, pending=enforcement)
        except ValueError:
            if get_by_android_id(aid) is None:
                return None
    touch_last_seen(aid, ip)
    return get_by_android_id(aid)


def check_authorization(android_id: str, ip: Optional[str] = None) -> dict[str, Any]:
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
            "tablet_number": None,
            "name": None,
        }
    row = ensure_registered(aid, ip)
    base = {
        "enforcement_enabled": enforcement,
        "android_id": aid,
        "label": (row or {}).get("label"),
        "tablet_number": (row or {}).get("number"),
        "name": (row or {}).get("name"),
    }
    if not enforcement:
        return {**base, "authorized": True, "reason": "enforcement_disabled"}
    if not row:
        return {**base, "authorized": False, "reason": "not_registered"}
    if not row.get("enabled"):
        reason = "pending_approval" if row.get("pending") else "disabled"
        return {**base, "authorized": False, "reason": reason}
    return {**base, "authorized": True, "reason": "ok"}


# --- Configuración propia de cada tablet ---------------------------------


def _tablet_info(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "android_id": row["android_id"],
        "number": row["number"],
        "name": row["name"],
        "label": row["label"],
    }


def get_tablet_config_record(tablet_id: int) -> Optional[dict[str, Any]]:
    """
    Config efectiva de una tablet: la suya si la tiene, si no la común de la sucursal.
    `inherited=True` indica que aún usa la común.
    """
    from app.db import tablet_config_store as tcs

    row = get_by_id(tablet_id)
    if not row:
        return None
    with get_connection() as conn:
        raw = conn.execute(
            "SELECT config_json, config_revision, config_updated_at FROM authorized_tablets WHERE id = ?",
            (int(tablet_id),),
        ).fetchone()
    own: Any = None
    if raw and raw[0]:
        try:
            own = json.loads(raw[0])
        except json.JSONDecodeError:
            own = None
    if isinstance(own, dict):
        return {
            "revision": raw[1] or "own",
            "updated_at": raw[2],
            "config": tcs.merge_tablet_config_with_defaults(own),
            "inherited": False,
            "tablet": _tablet_info(row),
        }
    common = tcs.get_tablet_config_record()
    return {
        "revision": f"common:{common.get('revision')}",
        "updated_at": common.get("updated_at"),
        "config": common.get("config"),
        "inherited": True,
        "tablet": _tablet_info(row),
    }


def set_tablet_config(tablet_id: int, config: dict[str, Any]) -> Optional[dict[str, Any]]:
    from app.db import tablet_config_store as tcs

    if get_by_id(tablet_id) is None:
        return None
    to_store = tcs.merge_tablet_config_with_defaults(config if isinstance(config, dict) else None)
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE authorized_tablets
            SET config_json = ?, config_revision = ?, config_updated_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(to_store, ensure_ascii=False), str(uuid.uuid4()), now, now, int(tablet_id)),
        )
        conn.commit()
    return get_tablet_config_record(tablet_id)


def reset_tablet_config(tablet_id: int) -> Optional[dict[str, Any]]:
    """Descarta la config propia: la tablet vuelve a usar la común de la sucursal."""
    if get_by_id(tablet_id) is None:
        return None
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE authorized_tablets
            SET config_json = NULL, config_revision = NULL, config_updated_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, int(tablet_id)),
        )
        conn.commit()
    return get_tablet_config_record(tablet_id)
