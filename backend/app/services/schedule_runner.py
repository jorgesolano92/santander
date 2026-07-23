"""Motor de horarios: resolución de modo y bucle en segundo plano."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from app.db.schedule_store import WEEKDAY_KEYS
from app.db import schedule_store

log = logging.getLogger("schedule.runner")

_wake_event: Optional[asyncio.Event] = None
# Última franja resuelta por el motor. Solo se fuerza un cambio de modo cuando
# esta franja cambia (inicio de tramo nuevo), no mientras el modo manual difiera
# del horario vigente dentro de la misma franja.
_last_resolved_target: Optional[str] = None
_schedule_bootstrapped: bool = False


def notify_schedule_config_changed() -> None:
    if _wake_event is not None:
        _wake_event.set()


def parse_hhmm(value: str) -> int:
    raw = str(value or "00:00").strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError(f"Hora inválida: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Hora inválida: {value}")
    return hour * 60 + minute


def _slot_matches_minute(minute: int, start: int, end: int) -> tuple[bool, int]:
    """Devuelve (coincide, prioridad). Prioridad = minuto de inicio para desempatar solapes."""
    if start < end:
        if start <= minute < end:
            return True, start
        return False, 0
    if minute >= start:
        return True, start
    return False, 0


def _slot_matches_spill(minute: int, start: int, end: int) -> tuple[bool, int]:
    """Parte matutina de un tramo nocturno del día anterior."""
    if start < end:
        return False, 0
    if minute < end:
        return True, start
    return False, 0


def resolve_rule_key_at(dt: datetime, config: dict) -> Optional[str]:
    """
    Modo que debería estar activo según horarios.
    None = sin franja activa → mantener modo actual.
    """
    if not config.get("enabled"):
        return None

    days = config.get("days") or {}
    weekday = dt.weekday()
    day_key = WEEKDAY_KEYS[weekday]
    prev_key = WEEKDAY_KEYS[(weekday - 1) % 7]
    minute = dt.hour * 60 + dt.minute

    candidates: list[tuple[int, str]] = []

    for slot in days.get(day_key, []) or []:
        if not slot.get("active"):
            continue
        try:
            start = parse_hhmm(slot.get("start", "00:00"))
            end = parse_hhmm(slot.get("end", "00:00"))
        except ValueError:
            continue
        ok, priority = _slot_matches_minute(minute, start, end)
        if ok:
            rk = str(slot.get("rule_key") or "").strip()
            if rk:
                candidates.append((priority, rk))

    for slot in days.get(prev_key, []) or []:
        if not slot.get("active"):
            continue
        try:
            start = parse_hhmm(slot.get("start", "00:00"))
            end = parse_hhmm(slot.get("end", "00:00"))
        except ValueError:
            continue
        ok, priority = _slot_matches_spill(minute, start, end)
        if ok:
            rk = str(slot.get("rule_key") or "").strip()
            if rk:
                candidates.append((priority, rk))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _datetime_at_minute(day: date, minute: int) -> datetime:
    return datetime.combine(day, time(minute // 60, minute % 60))


def collect_future_checkpoints(now: datetime, config: dict, *, horizon_days: int = 3) -> list[datetime]:
    """Instantes en los que puede cambiar el modo resuelto (próximos días)."""
    points: set[datetime] = set()
    days = config.get("days") or {}
    base = now.date()

    for offset in range(horizon_days + 1):
        day = base + timedelta(days=offset)
        day_key = WEEKDAY_KEYS[day.weekday()]
        for slot in days.get(day_key, []) or []:
            try:
                start = parse_hhmm(slot.get("start", "00:00"))
                end = parse_hhmm(slot.get("end", "00:00"))
            except ValueError:
                continue
            points.add(_datetime_at_minute(day, start))
            if end > start:
                points.add(_datetime_at_minute(day, end))
            else:
                next_day = day + timedelta(days=1)
                points.add(_datetime_at_minute(next_day, 0))
                points.add(_datetime_at_minute(next_day, end))

    points.add(datetime.combine(base + timedelta(days=1), time(0, 0)))
    return sorted(p for p in points if p > now)


def seconds_until_next_checkpoint(now: datetime, config: dict) -> float:
    if not config.get("enabled"):
        return 30.0
    checkpoints = collect_future_checkpoints(now, config)
    if not checkpoints:
        return 3600.0
    delta = (checkpoints[0] - now).total_seconds()
    return max(1.0, min(delta, 3600.0))


def _apply_schedule_mode(rule_key: str) -> None:
    from app.api.routes import panel

    current = panel.api_v1_get_current_mode()
    if current == rule_key:
        return
    result = panel.api_v1_execute_rule_for_tablet(rule_key)
    if result.get("queued"):
        log.info("Horario: modo %s encolado (enclavamiento manual)", rule_key)
        return
    if result.get("executed") is False:
        log.warning("Horario: no se pudo activar %s: %s", rule_key, result.get("reason"))
        return
    log.info("Horario automático: modo activado %s (antes %s)", rule_key, current)


def _sync_schedule_target(target: Optional[str]) -> None:
    """
    Aplica el modo de horario solo al cambiar de franja.

    - Cambio manual dentro de la franja actual: se respeta hasta la siguiente.
    - Arranque del servicio: no fuerza el horario si ya hay un modo activo
      (p. ej. override manual persistido); solo aplica si no hay modo.
    """
    global _last_resolved_target, _schedule_bootstrapped
    from app.api.routes import panel

    if not _schedule_bootstrapped:
        _schedule_bootstrapped = True
        _last_resolved_target = target
        current = panel.api_v1_get_current_mode()
        if target and not current:
            _apply_schedule_mode(target)
            log.info(
                "Horario: arranque sin modo activo → aplicado %s",
                target,
            )
        else:
            log.info(
                "Horario: arranque respetando modo actual=%s (franja=%s)",
                current,
                target,
            )
        return

    if target == _last_resolved_target:
        return

    previous = _last_resolved_target
    _last_resolved_target = target
    if not target:
        log.info("Horario: sin franja activa (antes %s); se mantiene el modo actual", previous)
        return

    log.info("Horario: cambio de franja %s → %s", previous, target)
    _apply_schedule_mode(target)


async def schedule_background_loop() -> None:
    global _wake_event
    _wake_event = asyncio.Event()
    log.info("Bucle de horarios automáticos iniciado")

    while True:
        try:
            config = schedule_store.get_schedule_config()
            now = datetime.now()

            if config.get("enabled"):
                target = resolve_rule_key_at(now, config)
                await asyncio.to_thread(_sync_schedule_target, target)
            else:
                # Con horarios desactivados no se fuerza modo; al reactivar se
                # vuelve a evaluar solo si cambia la franja respecto a la última.
                pass

            sleep_s = seconds_until_next_checkpoint(now, config)
            try:
                await asyncio.wait_for(_wake_event.wait(), timeout=sleep_s)
                _wake_event.clear()
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Error en bucle de horarios: %s", exc)
            await asyncio.sleep(15)
