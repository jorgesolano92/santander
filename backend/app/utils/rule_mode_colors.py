"""Colores y etiquetas de modos (panel_rules), alineado con el frontend."""
from __future__ import annotations

import re

DEFAULT_MODE_COLORS: dict[str, str] = {
    "horario_automatico": "#22c55e",
    "horario_esclusa": "#3b82f6",
    "horario_extendido": "#eab308",
    "horario_autoservicio": "#a855f7",
    "horario_cerrado": "#6b7280",
    "horario_carga_cajero": "#f97316",
    "horario_manual": "#ef4444",
    "senal_de_incendio_activada": "#E85D04",
}

FALLBACK_COLOR = "#6b7280"
_HEX_COLOR = re.compile(r"^#[0-9a-f]{6}$", re.IGNORECASE)


def normalize_rule_color(raw: object | None, rule_key: str | None) -> str:
    value = str(raw or "").strip()
    if _HEX_COLOR.match(value):
        return value
    if rule_key:
        return DEFAULT_MODE_COLORS.get(rule_key, FALLBACK_COLOR)
    return FALLBACK_COLOR


def resolve_rule_color(rule_key: str | None, rules: dict[str, dict] | None) -> str | None:
    if not rule_key:
        return None
    rule = (rules or {}).get(rule_key) or {}
    return normalize_rule_color(rule.get("color"), rule_key)


def rule_key_to_label(rule_key: str | None) -> str | None:
    if not rule_key:
        return None
    return rule_key.replace("_", " ").title()
