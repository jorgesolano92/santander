"""Persistencia de configuración por defecto de tablets (una sucursal)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.data.tablet_config_defaults import clone_builtin_default_tablet_config
from app.db.session import get_connection


def _init_db() -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tablet_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            config_json TEXT NOT NULL,
            revision TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _row_to_record(row: tuple) -> dict:
    config = json.loads(row[0]) if row[0] else clone_builtin_default_tablet_config()
    return {
        "revision": row[1],
        "updated_at": row[2],
        "config": config,
    }


def get_tablet_config_record() -> dict:
    """Devuelve revision, updated_at y config (builtin si no hay fila guardada)."""
    _init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT config_json, revision, updated_at FROM tablet_config WHERE id=1")
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return {
            "revision": "builtin",
            "updated_at": None,
            "config": clone_builtin_default_tablet_config(),
        }
    try:
        return _row_to_record(row)
    except json.JSONDecodeError:
        return {
            "revision": "builtin",
            "updated_at": None,
            "config": clone_builtin_default_tablet_config(),
        }


def get_tablet_config() -> dict:
    return get_tablet_config_record()["config"]


def set_tablet_config(config: dict) -> dict:
    _init_db()
    revision = str(uuid.uuid4())
    updated_at = datetime.now(timezone.utc).isoformat()
    config_str = json.dumps(config, ensure_ascii=False)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM tablet_config WHERE id=1")
    exists = c.fetchone()
    if exists:
        c.execute(
            "UPDATE tablet_config SET config_json=?, revision=?, updated_at=? WHERE id=1",
            (config_str, revision, updated_at),
        )
    else:
        c.execute(
            "INSERT INTO tablet_config (id, config_json, revision, updated_at) VALUES (1, ?, ?, ?)",
            (config_str, revision, updated_at),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "revision": revision, "updated_at": updated_at}


def get_tablet_call_settings() -> dict:
    """Subconjunto tabletCall con fallback a settings de entorno en el consumidor."""
    cfg = get_tablet_config()
    tc = cfg.get("tabletCall")
    return tc if isinstance(tc, dict) else {}
