"""Locuciones: pulsa los relés del reproductor de audio (placa 1, OUT2–OUT4) ante eventos.

Eventos soportados:
  - ``mode_entered``: la sucursal entra en un modo (p. ej. ``horario_extendido``).
  - ``door_opened``: se abre una puerta (sensor) estando en un modo dado (o cualquiera).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from app.db import locution_store

log = logging.getLogger("locutions")

_UNSET = object()
_last_mode: Any = _UNSET
_last_fired: dict[str, float] = {}
_busy_outputs: set[str] = set()
_lock = threading.Lock()


def _write_output(code: str, on: bool) -> None:
    from app.services import zaguan_orchestrator as zo

    zo._set_output_direct(code, on)  # noqa: SLF001
    zo._notify_panel_outputs_written([code], on=on)  # noqa: SLF001


def _record(message: str, payload: dict[str, Any]) -> None:
    try:
        from app.db import system_events_store as ses

        ses.record_event("INFO", message, event_type="locution", source="locutions", payload=payload)
    except Exception:  # noqa: BLE001
        pass


def _pulse(code: str, seconds: float) -> None:
    try:
        _write_output(code, True)
        time.sleep(seconds)
    except Exception as e:  # noqa: BLE001
        log.warning("Locución %s: error activando relé: %s", code, e)
    finally:
        try:
            _write_output(code, False)
        except Exception as e:  # noqa: BLE001
            log.warning("Locución %s: error apagando relé: %s", code, e)
        with _lock:
            _busy_outputs.discard(code)


def play(code: str, seconds: float, *, reason: str, trigger_id: Optional[str] = None) -> bool:
    """Lanza el pulso en segundo plano; False si ese relé ya está sonando."""
    code = code.strip().upper()
    if code not in locution_store.LOCUTION_OUTPUTS:
        raise ValueError(f"Salida de locución no válida: {code}")
    with _lock:
        if code in _busy_outputs:
            return False
        _busy_outputs.add(code)
    threading.Thread(target=_pulse, args=(code, seconds), name=f"locution-{code}", daemon=True).start()
    _record(
        f"Locución «{locution_store.LOCUTION_OUTPUTS[code]}» ({reason})",
        {"output": code, "seconds": seconds, "trigger_id": trigger_id, "reason": reason},
    )
    return True


def _fire(event: str, *, mode: Optional[str], door: Optional[str] = None) -> None:
    try:
        triggers = locution_store.get_triggers()
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo leer la configuración de locuciones: %s", e)
        return
    now = time.monotonic()
    for t in triggers:
        if not t["enabled"] or t["event"] != event:
            continue
        if t["mode"] != "any" and t["mode"] != mode:
            continue
        if event == "door_opened" and t["door"] != "any" and t["door"] != door:
            continue
        last = _last_fired.get(t["id"], 0.0)
        if last and now - last < t["cooldown_seconds"]:
            continue
        reason = f"{event} {mode or ''} {door or ''}".strip()
        if play(t["output"], t["pulse_seconds"], reason=reason, trigger_id=t["id"]):
            _last_fired[t["id"]] = now


def on_mode_changed(mode: Optional[str]) -> None:
    """Llamado en cada cambio/restauración de modo; ignora el primero (arranque)."""
    global _last_mode
    previous = _last_mode
    _last_mode = mode
    if previous is _UNSET or not mode or mode == previous:
        return
    _fire("mode_entered", mode=mode)


def on_door_opened(door: str, mode: Optional[str]) -> None:
    _fire("door_opened", mode=mode, door=door)
