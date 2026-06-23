"""Persistencia y valores por defecto de horarios semanales del panel."""
from __future__ import annotations

import copy
import json
from typing import Any

from app.db.session import get_connection

WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

WEEKDAY_LABELS_ES = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
}


def _slot(
    start: str,
    end: str,
    rule_key: str,
    *,
    active: bool = True,
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "rule_key": rule_key,
        "active": active,
    }


def default_monday_slots() -> list[dict[str, Any]]:
    return [
        _slot("08:00", "15:00", "horario_automatico"),
        _slot("15:00", "16:00", "horario_autoservicio"),
        _slot("16:00", "18:00", "horario_carga_cajero"),
        _slot("18:00", "08:00", "horario_cerrado"),
        _slot("20:00", "22:00", "horario_esclusa", active=False),
    ]


def clone_default_schedules() -> dict[str, Any]:
    monday = default_monday_slots()
    days = {key: copy.deepcopy(monday) for key in WEEKDAY_KEYS}
    return {
        "enabled": False,
        "days": days,
        "location": default_location(),
    }


def default_location() -> dict[str, Any]:
    return {
        "address": "",
        "latitude": None,
        "longitude": None,
        "captured_at": None,
    }


def normalize_location(raw: Any) -> dict[str, Any]:
    base = default_location()
    if not isinstance(raw, dict):
        return base
    address = raw.get("address")
    if isinstance(address, str):
        base["address"] = address.strip()
    for key in ("latitude", "longitude"):
        val = raw.get(key)
        if val is None or val == "":
            base[key] = None
            continue
        try:
            base[key] = float(val)
        except (TypeError, ValueError):
            base[key] = None
    captured = raw.get("captured_at")
    if isinstance(captured, str) and captured.strip():
        base["captured_at"] = captured.strip()
    return base


def normalize_schedule_config(data: Any) -> dict[str, Any]:
    base = clone_default_schedules()
    if not isinstance(data, dict):
        return base
    if "enabled" in data:
        base["enabled"] = bool(data.get("enabled"))
    days_in = data.get("days")
    if isinstance(days_in, dict):
        for key in WEEKDAY_KEYS:
            slots = days_in.get(key)
            if isinstance(slots, list):
                base["days"][key] = copy.deepcopy(slots)
    base["location"] = normalize_location(data.get("location"))
    return base


def opening_hours_summary(cfg: dict | None = None) -> str:
    """Resumen legible del horario del día actual (para COCE / mapa)."""
    data = normalize_schedule_config(cfg) if cfg is not None else get_schedule_config()
    if not data.get("enabled"):
        return "Detección de horarios desactivada en consola"
    from datetime import datetime

    weekday_keys = WEEKDAY_KEYS
    key = weekday_keys[datetime.now().weekday()]
    label = WEEKDAY_LABELS_ES[key]
    slots = (data.get("days") or {}).get(key) or []
    active = [s for s in slots if isinstance(s, dict) and s.get("active", True)]
    if not active:
        return f"{label}: sin franjas activas"
    parts = [f"{s.get('start', '?')}–{s.get('end', '?')}" for s in active]
    return f"{label}: " + ", ".join(parts)


def _init_db() -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            config_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def get_schedule_config() -> dict:
    _init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT config_json FROM schedule_config WHERE id=1")
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return clone_default_schedules()
    try:
        data = json.loads(row[0])
        if not isinstance(data, dict):
            return clone_default_schedules()
        return normalize_schedule_config(data)
    except json.JSONDecodeError:
        return clone_default_schedules()


def set_schedule_config(config: dict) -> dict:
    _init_db()
    config = normalize_schedule_config(config)
    conn = get_connection()
    c = conn.cursor()
    config_str = json.dumps(config, ensure_ascii=False)
    c.execute("SELECT id FROM schedule_config WHERE id=1")
    exists = c.fetchone()
    if exists:
        c.execute("UPDATE schedule_config SET config_json=? WHERE id=1", (config_str,))
    else:
        c.execute("INSERT INTO schedule_config (id, config_json) VALUES (1, ?)", (config_str,))
    conn.commit()
    conn.close()
    return {"ok": True}
