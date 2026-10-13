"""Configuración de locuciones (disparos de relés del reproductor de audio de la placa 1)."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.db.session import get_connection

LOCUTION_OUTPUTS: dict[str, str] = {
    "OUT_01_02": "Locución Cajero Ocupado",
    "OUT_01_03": "Locución Pase Por Favor",
    "OUT_01_04": "Locución Por Su Seguridad",
}
EVENTS = ("mode_entered", "door_opened")
DOORS = ("any", "p1", "p2")
PULSE_MIN_S = 0.3
PULSE_MAX_S = 30.0

DEFAULT_TRIGGERS: list[dict[str, Any]] = [
    {
        "id": "bienvenida_extendido",
        "enabled": False,
        "label": "Bienvenido (horario extendido)",
        "event": "door_opened",
        "mode": "horario_extendido",
        "door": "p1",
        "output": "OUT_01_03",
        "pulse_seconds": 1.0,
        "cooldown_seconds": 10.0,
    },
]

_RULE_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS locution_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            config_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def normalize_trigger(raw: dict[str, Any]) -> dict[str, Any]:
    event = str(raw.get("event") or "mode_entered")
    if event not in EVENTS:
        raise ValueError(f"Evento no válido: {event}")
    output = str(raw.get("output") or "").strip().upper()
    if output not in LOCUTION_OUTPUTS:
        raise ValueError(f"Salida de locución no válida: {output}")
    mode = str(raw.get("mode") or "any").strip().lower()
    if mode != "any" and not _RULE_KEY_RE.match(mode):
        raise ValueError(f"Modo no válido: {mode}")
    door = str(raw.get("door") or "any").strip().lower()
    if door not in DOORS:
        raise ValueError(f"Puerta no válida: {door}")
    if event == "mode_entered" and mode == "any":
        raise ValueError("Un disparo por entrada en modo necesita un modo concreto")
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:10]),
        "enabled": bool(raw.get("enabled", True)),
        "label": str(raw.get("label") or LOCUTION_OUTPUTS[output])[:80],
        "event": event,
        "mode": mode,
        "door": door if event == "door_opened" else "any",
        "output": output,
        "pulse_seconds": _clamp(raw.get("pulse_seconds"), PULSE_MIN_S, PULSE_MAX_S, 1.0),
        "cooldown_seconds": _clamp(raw.get("cooldown_seconds"), 0.0, 600.0, 10.0),
    }


def get_triggers() -> list[dict[str, Any]]:
    _init_db()
    conn = get_connection()
    row = conn.execute("SELECT config_json FROM locution_settings WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return [dict(t) for t in DEFAULT_TRIGGERS]
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError):
        return [dict(t) for t in DEFAULT_TRIGGERS]
    out: list[dict[str, Any]] = []
    for item in data if isinstance(data, list) else []:
        try:
            out.append(normalize_trigger(item))
        except ValueError:
            continue
    return out


def set_triggers(triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_trigger(t) for t in triggers]
    _init_db()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO locution_settings (id, config_json) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json
        """,
        (json.dumps(normalized, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    return normalized
