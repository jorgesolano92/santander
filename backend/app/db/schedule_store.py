"""Persistencia de horarios semanales del panel."""
from __future__ import annotations

import json

from app.data.schedule_defaults import clone_default_schedules
from app.db.session import get_connection


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
