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
    }


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
        return data
    except json.JSONDecodeError:
        return clone_default_schedules()


def set_schedule_config(config: dict) -> dict:
    _init_db()
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
