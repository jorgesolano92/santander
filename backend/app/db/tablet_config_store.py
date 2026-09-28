"""Persistencia de configuración por defecto de tablets (una sucursal)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

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


def _merge_intercom(base: dict[str, Any], saved: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(base or {})
    if not isinstance(saved, dict):
        return out
    for k, v in saved.items():
        if v is None:
            continue
        # Cadena vacía no pisa un default ya relleno (migración CSIP/SIP/rtsp).
        if isinstance(v, str) and not v.strip() and str(out.get(k) or "").strip():
            continue
        out[k] = v
    return out


def _merge_door(base: dict[str, Any], saved: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(base or {})
    if not isinstance(saved, dict):
        return out
    out.update({k: v for k, v in saved.items() if k != "intercom"})
    out["intercom"] = _merge_intercom(base.get("intercom") or {}, saved.get("intercom"))
    return out


def merge_tablet_config_with_defaults(saved: dict[str, Any] | None) -> dict[str, Any]:
    """Rellena campos nuevos (CSIP/SIP/rtsp) desde fábrica sin pisar valores guardados."""
    base = clone_builtin_default_tablet_config()
    if not isinstance(saved, dict):
        return base
    merged: dict[str, Any] = {**base, **saved}
    base_doors = base.get("doors") if isinstance(base.get("doors"), list) else []
    saved_doors = saved.get("doors") if isinstance(saved.get("doors"), list) else []
    doors: list[dict[str, Any]] = []
    for i, def_door in enumerate(base_doors):
        s = saved_doors[i] if i < len(saved_doors) else None
        doors.append(_merge_door(def_door, s if isinstance(s, dict) else None))
    for i in range(len(base_doors), len(saved_doors)):
        s = saved_doors[i]
        if isinstance(s, dict):
            doors.append(s)
    merged["doors"] = doors
    for key in (
        "api",
        "network",
        "emergency",
        "tabletCall",
        "configLogin",
        "schedules",
        "visualization",
        "cargaCajero",
        "fireSignal",
    ):
        if isinstance(base.get(key), dict) and isinstance(saved.get(key), dict):
            merged[key] = {**base[key], **saved[key]}
    if isinstance(base.get("modes"), dict):
        modes = dict(base["modes"])
        saved_modes = saved.get("modes") if isinstance(saved.get("modes"), dict) else {}
        for mk, mv in saved_modes.items():
            if isinstance(mv, dict):
                modes[mk] = {**(modes.get(mk) or {}), **mv}
            else:
                modes[mk] = mv
        merged["modes"] = modes
    return merged


def _row_to_record(row: tuple) -> dict:
    raw = json.loads(row[0]) if row[0] else None
    config = merge_tablet_config_with_defaults(raw if isinstance(raw, dict) else None)
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
    # Persistir ya fusionado para que el panel y las tablets vean los mismos campos.
    to_store = merge_tablet_config_with_defaults(config if isinstance(config, dict) else None)
    revision = str(uuid.uuid4())
    updated_at = datetime.now(timezone.utc).isoformat()
    config_str = json.dumps(to_store, ensure_ascii=False)
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
    return {"ok": True, "revision": revision, "updated_at": updated_at, "config": to_store}


def get_tablet_call_settings() -> dict:
    """Subconjunto tabletCall con fallback a settings de entorno en el consumidor."""
    cfg = get_tablet_config()
    tc = cfg.get("tabletCall")
    return tc if isinstance(tc, dict) else {}
