"""Enrutado de pulsaciones: default (lógica histórica) + overrides por modo/sucursal."""
from __future__ import annotations

import copy
import json
from typing import Any, Optional

from app.db.session import get_connection

PULSADORES = ("p1", "p2", "p3", "p4")
ACTIONS = ("call", "open", "ignore")

# Comportamiento actual del orquestador (sucursal con cajero / zaguán).
DEFAULT_CALL_ROUTING: dict[str, dict[str, str]] = {
    "horario_manual": {"p1": "call", "p2": "call", "p3": "call", "p4": "call"},
    "horario_carga_cajero": {"p1": "call", "p2": "open", "p3": "call", "p4": "open"},
    "horario_extendido": {"p1": "open", "p2": "call", "p3": "open", "p4": "open"},
    "horario_automatico": {"p1": "open", "p2": "open", "p3": "open", "p4": "open"},
    "horario_esclusa": {"p1": "open", "p2": "open", "p3": "open", "p4": "open"},
    "horario_autoservicio": {"p1": "open", "p2": "open", "p3": "open", "p4": "open"},
    "horario_cerrado": {"p1": "open", "p2": "open", "p3": "open", "p4": "open"},
}

DEFAULTS_VERSION = 1


def _init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS call_routing_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            config_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _normalize_action(raw: Any) -> Optional[str]:
    val = str(raw or "").strip().lower()
    return val if val in ACTIONS else None


def _normalize_overrides(raw: Any) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    for mode, mapping in raw.items():
        mode_key = str(mode or "").strip().lower()
        if not mode_key.startswith("horario_"):
            continue
        if not isinstance(mapping, dict):
            continue
        cleaned: dict[str, str] = {}
        for pulsador, action in mapping.items():
            p = str(pulsador or "").strip().lower()
            if p not in PULSADORES:
                continue
            act = _normalize_action(action)
            if act:
                cleaned[p] = act
        if cleaned:
            out[mode_key] = cleaned
    return out


def get_defaults(*, extendido_p1_call_without_zaguan: bool = False) -> dict[str, dict[str, str]]:
    defaults = copy.deepcopy(DEFAULT_CALL_ROUTING)
    if extendido_p1_call_without_zaguan:
        defaults.setdefault("horario_extendido", {})
        defaults["horario_extendido"]["p1"] = "call"
        defaults["horario_extendido"]["p3"] = "call"
    return defaults


def get_overrides() -> dict[str, dict[str, str]]:
    _init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT config_json FROM call_routing_config WHERE id = 1"
    ).fetchone()
    conn.close()
    if not row or not row[0]:
        return {}
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict) and "overrides" in data:
        return _normalize_overrides(data.get("overrides"))
    return _normalize_overrides(data)


def set_overrides(overrides: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    cleaned = _normalize_overrides(overrides)
    payload = {"defaults_version": DEFAULTS_VERSION, "overrides": cleaned}
    _init_db()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO call_routing_config (id, config_json) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json
        """,
        (json.dumps(payload, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    return cleaned


def get_effective(
    *,
    extendido_p1_call_without_zaguan: bool = False,
) -> dict[str, dict[str, str]]:
    effective = get_defaults(
        extendido_p1_call_without_zaguan=extendido_p1_call_without_zaguan
    )
    for mode, mapping in get_overrides().items():
        effective.setdefault(mode, {})
        effective[mode].update(mapping)
    return effective


def resolve_action(
    mode: Optional[str],
    pulsador: str,
    *,
    extendido_p1_call_without_zaguan: bool = False,
) -> str:
    """Devuelve call | open | ignore. Sin modo conocido → open."""
    mode_key = str(mode or "").strip().lower()
    p = str(pulsador or "").strip().lower()
    if p not in PULSADORES:
        return "ignore"
    effective = get_effective(
        extendido_p1_call_without_zaguan=extendido_p1_call_without_zaguan
    )
    if mode_key in effective and p in effective[mode_key]:
        return effective[mode_key][p]
    return "open"


def public_status(*, extendido_p1_call_without_zaguan: bool = False) -> dict[str, Any]:
    defaults = get_defaults(
        extendido_p1_call_without_zaguan=extendido_p1_call_without_zaguan
    )
    overrides = get_overrides()
    return {
        "defaults_version": DEFAULTS_VERSION,
        "pulsadores": list(PULSADORES),
        "actions": list(ACTIONS),
        "defaults": defaults,
        "overrides": overrides,
        "effective": get_effective(
            extendido_p1_call_without_zaguan=extendido_p1_call_without_zaguan
        ),
    }
