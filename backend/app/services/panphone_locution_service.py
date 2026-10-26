"""Locuciones Panphone (CSIP ``audio_play.php``) en horario extendido / autoservicio.

Actuaciones (videoportero exterior ``p1``):
  1. ``pase_por_favor`` — pulsador exterior P1 con todos los IN de cajero ocupado en reposo.
  2. ``bienvenido_entidad`` — flanco a excitado de cualquiera de esos IN (una vez por ciclo).
  3. ``cajero_ocupado`` — pulsador exterior P1 con algún IN excitado.
  4. ``demora_operacion`` — algún IN excitado de forma continua más de N segundos.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from app.core.config import settings

log = logging.getLogger("panphone_locutions")

LOCUTION_MODES = frozenset({"horario_extendido", "horario_autoservicio"})
LOC_PASE = "pase_por_favor"
LOC_BIENVENIDO = "bienvenido_entidad"
LOC_CAJERO = "cajero_ocupado"
LOC_DEMORA = "demora_operacion"

_lock = threading.Lock()
_last_any_occupied = False
_bienvenido_armed = True  # True = el próximo flanco a ocupado puede disparar bienvenido
_occupied_since: dict[str, float] = {}
_demora_fired_for: set[str] = set()


def _atm_input_codes() -> tuple[str, ...]:
    raw = (getattr(settings, "csip_atm_occupied_inputs", "") or "").strip()
    if not raw:
        return ("IN_01_11", "IN_02_10", "IN_03_10")
    return tuple(c.strip().upper() for c in raw.split(",") if c.strip())


def _device_id() -> str:
    return (getattr(settings, "csip_locution_device_id", None) or "p1").strip().lower() or "p1"


def _delay_seconds() -> float:
    try:
        return max(30.0, float(getattr(settings, "csip_atm_delay_locution_seconds", 300) or 300))
    except (TypeError, ValueError):
        return 300.0


def _mode_ok(mode: Optional[str]) -> bool:
    return bool(mode) and mode in LOCUTION_MODES


def _read_input(code: str) -> bool:
    from app.services import zaguan_orchestrator as zo

    return bool(zo._read_input(code))  # noqa: SLF001


def _any_atm_occupied() -> tuple[bool, dict[str, bool]]:
    states: dict[str, bool] = {}
    any_on = False
    for code in _atm_input_codes():
        try:
            on = _read_input(code)
        except Exception:  # noqa: BLE001
            on = False
        states[code] = on
        if on:
            any_on = True
    return any_on, states


def _record(message: str, payload: dict[str, Any]) -> None:
    try:
        from app.db import system_events_store as ses

        ses.record_event(
            "INFO",
            message,
            event_type="panphone_locution",
            source="panphone_locutions",
            payload=payload,
        )
    except Exception:  # noqa: BLE001
        pass


def play(locucion: str, *, reason: str) -> bool:
    """POST ``audio_play.php`` en segundo plano. False si CSIP desactivado."""
    from app.csip import client as csip_client

    if not csip_client.is_configured():
        log.debug("Locución %s omitida (CSIP no configurado)", locucion)
        return False

    name = (locucion or "").strip()
    if not name:
        return False

    device_id = _device_id()
    timeout = float(getattr(settings, "csip_audio_timeout_s", 8.0) or 8.0)

    def _run() -> None:
        try:
            csip_client.audio_play(name, device_id=device_id, timeout_s=timeout)
            log.info("Locución Panphone %s OK (%s, device=%s)", name, reason, device_id)
        except Exception as e:  # noqa: BLE001
            log.warning("Locución Panphone %s falló (%s): %s", name, reason, e)

    threading.Thread(target=_run, name=f"csip-audio-{name}", daemon=True).start()
    _record(
        f"Locución Panphone «{name}» ({reason})",
        {"locucion": name, "reason": reason, "device_id": device_id},
    )
    return True


def on_exterior_p1_pressed(mode: Optional[str]) -> Optional[str]:
    """Actuaciones 1 y 3 al pulsar el botón de entrada exterior P1."""
    if not _mode_ok(mode):
        return None
    any_on, states = _any_atm_occupied()
    if any_on:
        play(LOC_CAJERO, reason=f"p1 + cajero ocupado ({mode})")
        return LOC_CAJERO
    play(LOC_PASE, reason=f"p1 + cajeros en reposo ({mode})")
    return LOC_PASE


def poll_atm_occupancy(mode: Optional[str]) -> None:
    """Actuaciones 2 y 4: flancos de ocupación y demora > N s."""
    global _last_any_occupied, _bienvenido_armed

    any_on, states = _any_atm_occupied()
    now = time.monotonic()

    with _lock:
        if not _mode_ok(mode):
            # Fuera de modo: resetear ciclo de bienvenida/demora sin reproducir.
            _last_any_occupied = any_on
            if not any_on:
                _bienvenido_armed = True
                _occupied_since.clear()
                _demora_fired_for.clear()
            return

        # Actuación 2: flanco reposo → ocupado, una sola vez hasta volver a reposo total.
        if any_on and not _last_any_occupied and _bienvenido_armed:
            _bienvenido_armed = False
            play(LOC_BIENVENIDO, reason=f"flanco cajero ocupado ({mode})")

        if not any_on:
            _bienvenido_armed = True
            _occupied_since.clear()
            _demora_fired_for.clear()
        else:
            delay_s = _delay_seconds()
            for code, on in states.items():
                if not on:
                    _occupied_since.pop(code, None)
                    _demora_fired_for.discard(code)
                    continue
                since = _occupied_since.get(code)
                if since is None:
                    _occupied_since[code] = now
                    continue
                if code not in _demora_fired_for and (now - since) >= delay_s:
                    _demora_fired_for.add(code)
                    play(
                        LOC_DEMORA,
                        reason=f"{code} ocupado >{delay_s:.0f}s ({mode})",
                    )

        _last_any_occupied = any_on
