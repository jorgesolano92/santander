"""Reexporta defaults de horarios (compatibilidad)."""
from app.db.schedule_store import (  # noqa: F401
    WEEKDAY_KEYS,
    WEEKDAY_LABELS_ES,
    clone_default_schedules,
    default_monday_slots,
)

def get_builtin_default_schedules():
    return clone_default_schedules()
