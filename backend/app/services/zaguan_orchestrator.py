"""
Orquestador zaguán: LEDs ESP32 + apertura Modbus según modo operativo.

Modos implementados: horario_automatico, horario_esclusa, horario_autoservicio,
horario_extendido, horario_carga_cajero, horario_manual, horario_cerrado.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import Coroutine
from typing import Any, Literal, Optional, Union

from app.db import system_events_store as ses

log = logging.getLogger(__name__)

EstadoLed = Literal["libre", "ocupado", "abriendo", "apagado"]
PuertaId = Literal["p1", "p2"]
PulsadorId = Literal["p1", "p2", "p3", "p4"]

SUPPORTED_MODES = frozenset(
    {
        "horario_automatico",
        "horario_esclusa",
        "horario_autoservicio",
        "horario_extendido",
        "horario_carga_cajero",
        "horario_manual",
        "horario_cerrado",
    }
)
INTERLOCK_MODES = frozenset({"horario_esclusa", "horario_extendido"})
STRICT_INTERLOCK_MODES = frozenset({"horario_autoservicio", "horario_cerrado"})
WINHOSE_MODES = frozenset({"horario_autoservicio", "horario_cerrado"})

# WinHose: IN3 por placa. Cerrado=ON, abierto=OFF → flanco ON→OFF → ventana 15 s.
WINHOSE_INPUT_BY_DOOR: dict[PuertaId, str] = {
    "p1": "IN_02_03",
    "p2": "IN_03_03",
}
WINHOSE_WINDOW_SECONDS = 15.0
# Libre WinHose: parpadeo verde (solo durante ventana 15 s; reposo vuelve a fijo).
WINHOSE_LIBRE_PARPADEO_MS = 1000
# Tras cambio de modo: no disparar WinHose por flancos espurios al re-leer IN_03.
WINHOSE_EDGE_GRACE_S = 3.0
# Presencia zaguán (placa 2 IN10 + placa 3 IN10): único criterio para bloquear entradas P1/P2.
OCCUPANCY_INPUT_CODES = ("IN_02_10", "IN_03_10")
ZAGUAN_OCCUPANCY_MODES = frozenset({"horario_autoservicio", "horario_extendido"})
# Extendido p2 exterior: llamada a consola/tablet antes de apertura de P2.
EXTENDIDO_TABLET_CALL_ENABLED = True
DOOR_PULSE_OFF_SECONDS = 5.0
# Tras el pulso Modbus (~5 s), si el inductivo no marca apertura, volver LED a libre.
DOOR_LED_REPOSO_AFTER_S = DOOR_PULSE_OFF_SECONDS + 1.5
# Autoservicio: no liberar la puerta opuesta hasta cierre real (sensor) o tiempo máximo.
DOOR_AUTOSERVICIO_INTERLOCK_MAX_S = 90.0
DOOR_AUTOSERVICIO_MIN_MANEUVER_S = 3.0
DOOR_AUTOSERVICIO_CLOSE_DEBOUNCE_POLLS = 3
# Si IN_xx_04 no marcó apertura: cerrar interbloqueo tras lecturas estables de «cerrada».
DOOR_AUTOSERVICIO_FALLBACK_CLOSE_S = DOOR_PULSE_OFF_SECONDS + 4.0

INITIAL_LED_BY_MODE: dict[str, dict[PulsadorId, EstadoLed]] = {
    "horario_automatico": {
        "p1": "libre",
        "p2": "libre",
        "p3": "libre",
        "p4": "libre",
    },
    "horario_esclusa": {
        "p1": "libre",
        "p2": "libre",
        "p3": "libre",
        "p4": "libre",
    },
    "horario_autoservicio": {
        "p1": "libre",
        "p2": "ocupado",
        "p3": "libre",
        "p4": "libre",
    },
    "horario_extendido": {
        "p1": "libre",
        "p2": "libre",
        "p3": "libre",
        "p4": "libre",
    },
    "horario_carga_cajero": {
        # Reposo carga cajero:
        # p1 exterior = ocupado, p1 interior = libre, p2 exterior = abriendo, p2 interior = abriendo.
        "p1": "ocupado",
        "p2": "abriendo",
        "p3": "libre",
        "p4": "abriendo",
    },
    "horario_manual": {
        # Reposo manual: 4 canales en libre.
        "p1": "libre",
        "p2": "libre",
        "p3": "libre",
        "p4": "libre",
    },
    "horario_cerrado": {
        # Reposo cerrado: exteriores apagado, interiores libre.
        "p1": "apagado",
        "p2": "apagado",
        "p3": "libre",
        "p4": "libre",
    },
}

EXTERIOR_PULSADOR: dict[PuertaId, PulsadorId] = {"p1": "p1", "p2": "p2"}

OPPOSITE_DOOR: dict[PuertaId, PuertaId] = {"p1": "p2", "p2": "p1"}

PULSADOR_TO_DOOR: dict[PulsadorId, PuertaId] = {
    "p1": "p1",
    "p2": "p2",
    "p3": "p1",
    "p4": "p2",
}

PULSADOR_TO_INTERFONO_RULE: dict[PulsadorId, str] = {
    "p1": "interfono_puerta_calle_exterior",
    "p2": "interfono_puerta_oficina_exterior",
    "p3": "interfono_puerta_calle_interior",
    "p4": "interfono_puerta_oficina_interior",
}

DOOR_TO_LED_CHANNELS: dict[PuertaId, tuple[PulsadorId, PulsadorId]] = {
    "p1": ("p1", "p3"),
    "p2": ("p2", "p4"),
}

DOOR_OPEN_SENSOR: dict[PuertaId, str] = {
    "p1": "IN_02_04",
    "p2": "IN_03_04",
}

DOOR_OPEN_OUTPUT: dict[PuertaId, str] = {
    "p1": "OUT_02_07",
    "p2": "OUT_03_07",
}

# Cierres mecánicos (llave EMICOM) que el interfono apaga temporalmente al abrir.
DOOR_LOCK_OUTPUTS: dict[PuertaId, tuple[str, ...]] = {
    "p1": ("OUT_02_01", "OUT_02_02"),
    "p2": ("OUT_03_01", "OUT_03_02"),
}
DOOR_BOARD_ID: dict[PuertaId, int] = {"p1": 2, "p2": 3}
# panel_rules interfono exterior/interior: pulse_seconds = 2
DOOR_INTERFONO_PULSE_SECONDS = 2.0
# Tras sensor "cerrada": espera antes de reactivar bulones (evita pinzar la hoja).
DOOR_LOCK_RESTORE_DELAY_S = 2.0
# Al entrar a oficina cerrada: espera tras cierre confirmado antes de echar bulones.
CLOSED_MODE_BOLT_SETTLE_S = 2.0
# Timeout máximo esperando que las puertas cierren al forzar horario_cerrado.
CLOSED_MODE_DOOR_CLOSE_TIMEOUT_S = 45.0
CLOSED_MODE_DOOR_POLL_S = 0.4
# Manual/carga tablet: fallback LED reposo más corto que el pulso genérico (5 s).
TABLET_LED_REPOSO_AFTER_S = DOOR_INTERFONO_PULSE_SECONDS + 2.0

DOOR_OPEN_RULE_PREFIXES = (
    "radares_interior_puerta_",
    "radares_exterior_puerta_",
    "interfono_puerta_",
    "pulsador_emergencia_puerta_",
    "apertura_remota_coce_puerta_",
)

ORCHESTRATOR_ENABLED = True
LED_DEVICE_SYNC = True
_CAPTURE_ONLY = os.getenv("ZAGUAN_PULSACION_CAPTURE_ONLY", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
MODBUS_ON_PULSACION = not _CAPTURE_ONLY

_led_states: dict[PulsadorId, EstadoLed] = {
    "p1": "apagado",
    "p2": "apagado",
    "p3": "apagado",
    "p4": "apagado",
}
_current_mode: Optional[str] = None
_door_was_open: dict[PuertaId, bool] = {"p1": False, "p2": False}
_pending_abriendo: dict[PuertaId, bool] = {"p1": False, "p2": False}
_abriendo_since: dict[PuertaId, float] = {"p1": 0.0, "p2": 0.0}
# Tiempo continuo con sensor abierto (alerta door_held → COCE).
_door_open_since: dict[PuertaId, float] = {"p1": 0.0, "p2": 0.0}
_door_held_alert_active: dict[PuertaId, bool] = {"p1": False, "p2": False}
# Manual/carga: el inductivo debe marcar apertura antes de aceptar flanco de cierre.
_saw_open_during_pending: dict[PuertaId, bool] = {"p1": False, "p2": False}
_led_state_lock = threading.RLock()
_led_push_serial = threading.Lock()
# Autoservicio: bloquea la puerta opuesta hasta cierre confirmado (IN_xx_04).
_door_interlock_active: dict[PuertaId, bool] = {"p1": False, "p2": False}
_saw_open_while_interlock: dict[PuertaId, bool] = {"p1": False, "p2": False}
_door_closed_streak: dict[PuertaId, int] = {"p1": 0, "p2": 0}

# WinHose: flanco cerrado→abierto (ON→OFF); ventanas e intermitentes independientes por puerta.
_winhose_last_closed: dict[str, bool] = {}
_winhose_window_until: dict[PuertaId, float] = {"p1": 0.0, "p2": 0.0}
_winhose_intermittent_tasks: dict[PuertaId, Optional[asyncio.Task]] = {
    "p1": None,
    "p2": None,
}
_winhose_mode_changed_at: float = 0.0
_async_loop: Optional[asyncio.AbstractEventLoop] = None
ScheduledTask = Union[asyncio.Task[Any], asyncio.Future[Any]]


def bind_async_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Registra el loop principal (uvicorn) para tareas desde hilos síncronos."""
    global _async_loop
    _async_loop = loop


def _schedule_coro(coro: Coroutine[Any, Any, Any]) -> Optional[ScheduledTask]:
    try:
        loop = asyncio.get_running_loop()
        return loop.create_task(coro)
    except RuntimeError:
        if _async_loop is not None and _async_loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, _async_loop)
    log.warning("No hay event loop para programar tarea zaguán")
    return None


def _cancel_scheduled(task: Optional[ScheduledTask]) -> None:
    if task is None:
        return
    task.cancel()

# Extendido: p2 exterior → llamada consola (sin Modbus); p3 intermitente hasta COCE/p4.
_extendido_p2_call_pending: bool = False
_p3_intermittent: bool = False
_p3_intermittent_task: Optional[asyncio.Task] = None
# Carga cajero: p1/p3 disparan llamada a consola; apertura de P1 tras confirmación.
_carga_p1_call_pending: bool = False
# Manual/carga/extendido: bulones (OUT_x_01/02) activos por el modo; se sueltan al abrir
# y se restauran al cerrar con el mismo retardo que en modo cerrado.
TABLET_LOCK_RELEASE_MODES = frozenset(
    {"horario_manual", "horario_carga_cajero", "horario_extendido"}
)
_locks_to_restore: dict[PuertaId, list[str]] = {"p1": [], "p2": []}
_lock_restore_tasks: dict[PuertaId, Optional[ScheduledTask]] = {"p1": None, "p2": None}


def get_led_states() -> dict[str, EstadoLed]:
    return dict(_led_states)


def set_led_state_from_console(canal: str, estado: EstadoLed) -> None:
    """Sincroniza el orquestador tras un cambio manual desde consola (el ESP ya fue actualizado)."""
    ch: PulsadorId = canal if canal in ("p1", "p2", "p3", "p4") else f"p{int(canal)}"
    if ch not in _led_states:
        return
    with _led_state_lock:
        _led_states[ch] = estado
        _sync_led_memory()
    _publish_zaguan_led_state()
    # La placa Panphone no recibe el push ESP32; reenviar p1/p2 por CSIP.
    if ch in ("p1", "p2"):
        _schedule_csip_led_push({ch: estado})


def get_autoservicio_status() -> dict[str, Any]:
    """Estado auxiliar (WinHose, intermitente) para depuración/API."""
    now = time.monotonic()
    winhose_by_door: dict[str, dict[str, Any]] = {}
    for door in ("p1", "p2"):
        until = _winhose_window_until.get(door, 0.0)
        active = until > 0 and now < until
        task = _winhose_intermittent_tasks.get(door)
        winhose_by_door[door] = {
            "active": active,
            "remaining_s": max(0.0, until - now) if until else 0.0,
            "input": WINHOSE_INPUT_BY_DOOR[door],
            "intermittent_scheduled": task is not None and not task.done(),
        }
    return {
        "winhose_window_active": _winhose_window_active_for("p2"),
        "winhose_window_remaining_s": winhose_by_door["p2"]["remaining_s"],
        "winhose_by_door": winhose_by_door,
        "winhose_inputs": dict(WINHOSE_INPUT_BY_DOOR),
        "winhose_libre_parpadeo": {
            ch: _should_libre_parpadeo_winhose(ch) for ch in ("p1", "p2", "p3", "p4")
        },
        "zaguan_presence_inputs": list(OCCUPANCY_INPUT_CODES),
        "zaguan_occupied": _zaguan_occupied(),
        "extendido_p2_call_pending": _extendido_p2_call_pending,
        "p3_intermittent": _p3_intermittent,
        "carga_p1_call_pending": _carga_p1_call_pending,
    }


def get_current_mode() -> Optional[str]:
    return _current_mode


def _import_panel():
    from app.api.routes import panel

    return panel


def _read_panel_mode() -> Optional[str]:
    try:
        return _import_panel().api_v1_get_current_mode()
    except Exception:  # noqa: BLE001
        return _current_mode


def _import_zaguan_mem():
    import zaguan_esp32

    return zaguan_esp32


def _import_led_client():
    from app.services import zaguan_led_client

    return zaguan_led_client


def _read_input(code: str) -> bool:
    return bool(_import_panel().api_v1_read_input_by_code(code))


def _rule_opens_door(rule_key: str) -> Optional[PuertaId]:
    if "puerta_calle" in rule_key or rule_key.endswith("_calle"):
        return "p1"
    if "puerta_oficina" in rule_key or rule_key.endswith("_oficina"):
        return "p2"
    return None


def _schedule_led_device_push(
    states: dict[PulsadorId, EstadoLed],
    *,
    push_order: Optional[tuple[PulsadorId, ...]] = None,
) -> None:
    """HTTP a ESP32 en segundo plano: no bloquear ciclo Modbus / reglas automáticas."""
    if not LED_DEVICE_SYNC:
        return
    snapshot = dict(states)
    order = push_order

    async def _worker() -> None:
        def _run() -> None:
            with _led_push_serial:
                _push_leds_to_device(snapshot, push_order=order)

        await asyncio.to_thread(_run)

    _schedule_coro(_worker())


def _csip_led_cmd_for_estado(ch: PulsadorId, est: EstadoLed) -> str:
    """
    Comando compacto CSIP (cmd) con animación/color.
    Formato OpenAPI: 'LED:ACCION' o 'LED:ACCION:VALOR'
    (ej. p1:green, p1:rainbow, p1:efectovuelta:red).
    """
    if est == "libre":
        if _should_libre_parpadeo_winhose(ch):
            return f"{ch}:efectovuelta:green"
        return f"{ch}:green"
    if est == "ocupado":
        return f"{ch}:efectovuelta:red"
    if est == "abriendo":
        return f"{ch}:rainbow"
    if est == "apagado":
        return f"{ch}:off"
    return f"{ch}:{est}"


def _schedule_csip_led_push(states: dict[PulsadorId, EstadoLed]) -> None:
    """Empuja p1/p2 a Panphone vía CSIP led_control (estado + animación). Best-effort."""
    csip_states = {ch: est for ch, est in states.items() if ch in ("p1", "p2")}
    if not csip_states:
        return

    async def _worker() -> None:
        def _run() -> None:
            try:
                from app.csip import client as csip_client
                from app.csip.schemas import LedControlRequest
            except Exception as e:  # noqa: BLE001
                log.debug("CSIP led import: %s", e)
                return
            if not csip_client.is_configured():
                return
            for ch, est in csip_states.items():
                cmd = _csip_led_cmd_for_estado(ch, est)
                try:
                    # Animación/color por cmd + estado lógico (API Custom1).
                    csip_client.led_control(
                        LedControlRequest(cmd=cmd, led=ch, estado=est)
                    )
                    log.info("CSIP led_control %s cmd=%s estado=%s OK", ch, cmd, est)
                except Exception as e:  # noqa: BLE001
                    # Panphone a veces responde "could not persist" aunque el LED cambie.
                    log.warning(
                        "CSIP led_control %s cmd=%s estado=%s: %s", ch, cmd, est, e
                    )

        await asyncio.to_thread(_run)

    _schedule_coro(_worker())


def _apply_led_channels(channels: tuple[PulsadorId, ...], estado: EstadoLed) -> None:
    payload = {ch: estado for ch in channels}
    with _led_state_lock:
        for ch in channels:
            _led_states[ch] = estado
        _sync_led_memory()
    _publish_zaguan_led_state()
    _schedule_led_device_push(payload, push_order=channels)
    _schedule_csip_led_push(payload)


def _led_states_match(target: dict[PulsadorId, EstadoLed]) -> bool:
    return all(_led_states.get(ch) == est for ch, est in target.items())


def _led_map_push_order(
    states: dict[PulsadorId, EstadoLed],
    *,
    priority_door: Optional[PuertaId] = None,
) -> tuple[PulsadorId, ...]:
    """Pareja de puerta prioritaria primero (exterior+interior juntos en el ESP32)."""
    present = set(states)
    if priority_door is not None:
        primary = [ch for ch in DOOR_TO_LED_CHANNELS[priority_door] if ch in present]
        secondary = [
            ch
            for ch in DOOR_TO_LED_CHANNELS[OPPOSITE_DOOR[priority_door]]
            if ch in present
        ]
        return tuple(primary + secondary)
    for door in ("p1", "p2"):
        chs = DOOR_TO_LED_CHANNELS[door]
        if any(states.get(ch) == "abriendo" for ch in chs if ch in present):
            primary = [ch for ch in chs if ch in present]
            secondary = [
                ch
                for ch in DOOR_TO_LED_CHANNELS[OPPOSITE_DOOR[door]]
                if ch in present
            ]
            return tuple(primary + secondary)
    return tuple(ch for ch in ("p1", "p2", "p3", "p4") if ch in present)


def _apply_led_map(
    states: dict[PulsadorId, EstadoLed],
    *,
    priority_door: Optional[PuertaId] = None,
) -> None:
    if _led_states_match(states):
        return
    push_order = _led_map_push_order(states, priority_door=priority_door)
    with _led_state_lock:
        for ch, est in states.items():
            _led_states[ch] = est
        _sync_led_memory()
    _publish_zaguan_led_state()
    _schedule_led_device_push(states, push_order=push_order)
    _schedule_csip_led_push(states)


def _sync_led_memory() -> None:
    try:
        z = _import_zaguan_mem()
        for ch, est in _led_states.items():
            z.actualizar_estado_canal(ch, est)
    except Exception as e:  # noqa: BLE001
        log.debug("Sync memoria zaguan_esp32: %s", e)


def _publish_zaguan_led_state() -> None:
    """Notifica consola (WebSocket) sin bloquear el hilo del orquestador."""
    try:
        from app.services import panel_live_hub as plh

        plh.publish_sync(
            {
                "type": "zaguan_led",
                "payload": {
                    "leds": dict(_led_states),
                    "mode": _current_mode,
                },
            }
        )
    except Exception as e:  # noqa: BLE001
        log.debug("Publish zaguan_led WS: %s", e)


LED_LIBRE_COLOR = (0, 200, 0)
LED_OCUPADO_COLOR = (200, 0, 0)


def _config_led_estado_fijo(ch: PulsadorId, estado: EstadoLed, color: tuple[int, int, int]) -> None:
    client = _import_led_client()
    client.config_estado(
        {
            "canal": int(ch[1]),
            "estado": estado,
            "color": list(color),
            "animacion": "fijo",
        }
    )


def _config_libre_fijo(ch: PulsadorId) -> None:
    """Libre: verde fijo en todos los modos (sin respiración)."""
    _config_led_estado_fijo(ch, "libre", LED_LIBRE_COLOR)


def _config_libre_parpadeo(ch: PulsadorId) -> None:
    """Libre WinHose: verde parpadeo durante ventana 15 s."""
    client = _import_led_client()
    client.config_estado(
        {
            "canal": int(ch[1]),
            "estado": "libre",
            "color": list(LED_LIBRE_COLOR),
            "animacion": "parpadeo",
            "velocidad": WINHOSE_LIBRE_PARPADEO_MS,
        }
    )


def _should_libre_parpadeo_winhose(ch: PulsadorId) -> bool:
    """Parpadeo solo en libre mientras dura la ventana WinHose."""
    if _current_mode not in WINHOSE_MODES or not _any_winhose_window_active():
        return False
    if _current_mode == "horario_autoservicio":
        return True
    if _current_mode == "horario_cerrado":
        return any(
            _winhose_window_active_for(door) and EXTERIOR_PULSADOR[door] == ch
            for door in _winhose_doors_for_mode(_current_mode)
        )
    return False


def _config_cerrado_exterior_ocupado_fijo(ch: PulsadorId) -> None:
    """Cerrado reposo: rojo fijo en exterior (Excel no usa parpadeo rojo en reposo)."""
    _config_led_estado_fijo(ch, "ocupado", LED_OCUPADO_COLOR)


def _push_leds_to_device(
    states: dict[PulsadorId, EstadoLed],
    *,
    push_order: Optional[tuple[PulsadorId, ...]] = None,
) -> None:
    client = _import_led_client()
    order = push_order or tuple(states.keys())
    for ch in order:
        est = states.get(ch)
        if est is None:
            continue
        try:
            if est == "libre":
                if _should_libre_parpadeo_winhose(ch):
                    _config_libre_parpadeo(ch)
                else:
                    _config_libre_fijo(ch)
            elif (
                _current_mode == "horario_cerrado"
                and ch in ("p1", "p2")
                and est == "ocupado"
            ):
                _config_cerrado_exterior_ocupado_fijo(ch)
            client.set_estado_canal(ch, est)
        except client.ZaguanLedClientError as e:
            log.warning("LED ESP32 canal %s -> %s: %s", ch, est, e)


def _record(event_type: str, message: str, payload: dict[str, Any]) -> None:
    try:
        ses.record_event(
            "INFO",
            message,
            event_type=event_type,
            source="zaguan_orchestrator",
            payload=payload,
        )
    except Exception:  # noqa: BLE001
        pass


def _winhose_doors_for_mode(mode: Optional[str]) -> tuple[PuertaId, ...]:
    if mode == "horario_autoservicio":
        return ("p2",)
    if mode == "horario_cerrado":
        return ("p1", "p2")
    return ()


def _seed_winhose_baseline() -> None:
    """Estado actual de llaves al entrar en modo (evita flanco falso tras reset)."""
    if _current_mode not in WINHOSE_MODES:
        return
    for door in _winhose_doors_for_mode(_current_mode):
        code = WINHOSE_INPUT_BY_DOOR[door]
        try:
            _winhose_last_closed[code] = bool(_read_input(code))
        except Exception as e:  # noqa: BLE001
            log.debug("WinHose seed %s: %s", code, e)


def _winhose_window_active_for(door: PuertaId) -> bool:
    until = _winhose_window_until.get(door, 0.0)
    return until > 0 and time.monotonic() < until


def _any_winhose_window_active() -> bool:
    return any(_winhose_window_active_for(d) for d in ("p1", "p2"))


def _stop_winhose_intermittent(door: PuertaId) -> None:
    _cancel_scheduled(_winhose_intermittent_tasks.get(door))
    _winhose_intermittent_tasks[door] = None


def _stop_all_winhose_intermittent() -> None:
    for door in ("p1", "p2"):
        _stop_winhose_intermittent(door)


def _clear_winhose_window(door: PuertaId) -> None:
    _winhose_window_until[door] = 0.0
    _stop_winhose_intermittent(door)


def _reset_winhose_state() -> None:
    _winhose_last_closed.clear()
    for door in ("p1", "p2"):
        _winhose_window_until[door] = 0.0
    _stop_all_winhose_intermittent()


def _reset_extendido_state() -> None:
    global _extendido_p2_call_pending, _p3_intermittent, _p3_intermittent_task
    _extendido_p2_call_pending = False
    _p3_intermittent = False
    if _p3_intermittent_task and not _p3_intermittent_task.done():
        _p3_intermittent_task.cancel()
    _p3_intermittent_task = None


def _reset_carga_state() -> None:
    global _carga_p1_call_pending
    _carga_p1_call_pending = False


def _stop_p3_intermittent() -> None:
    global _p3_intermittent, _p3_intermittent_task
    _p3_intermittent = False
    if _p3_intermittent_task and not _p3_intermittent_task.done():
        _p3_intermittent_task.cancel()
    _p3_intermittent_task = None


async def _p3_intermittent_loop() -> None:
    """Extendido: p3 intermitente mientras espera autorización consola."""
    client = _import_led_client()
    try:
        while _extendido_p2_call_pending:
            try:
                await asyncio.to_thread(client.set_estado_canal, "p3", "libre")
                await asyncio.to_thread(
                    client.config_flash,
                    {"color": [0, 200, 0], "n_flashes": 2, "duracion_ms": 350},
                )
            except Exception as e:  # noqa: BLE001
                log.debug("Flash intermitente p3: %s", e)
            await asyncio.sleep(0.9)
    except asyncio.CancelledError:
        pass


def _clear_extendido_p2_call() -> None:
    global _extendido_p2_call_pending
    if not _extendido_p2_call_pending:
        return
    _extendido_p2_call_pending = False
    _stop_p3_intermittent()
    if _current_mode == "horario_extendido":
        with _led_state_lock:
            _led_states["p3"] = "libre"
            _sync_led_memory()
        _publish_zaguan_led_state()
        _schedule_led_device_push({"p3": "libre"})


def _start_extendido_p2_call() -> None:
    """p2 exterior: notifica consola y enciende p3 intermitente (sin abrir P2)."""
    global _extendido_p2_call_pending, _p3_intermittent, _p3_intermittent_task
    _extendido_p2_call_pending = True
    _p3_intermittent = True
    _apply_led_map(dict(INITIAL_LED_BY_MODE["horario_extendido"]))
    _record(
        "zaguan_extendido_call",
        "Extendido: llamada consola P2 (p3 intermitente)",
        {"pulsador": "p2", "mode": _current_mode},
    )
    log.info("Extendido: llamada consola P2 — p3 intermitente")
    try:
        loop = asyncio.get_running_loop()
        _p3_intermittent_task = loop.create_task(_p3_intermittent_loop())
    except RuntimeError:
        pass


def _carga_cajero_reposo() -> None:
    _apply_led_map(dict(INITIAL_LED_BY_MODE["horario_carga_cajero"]))


def _start_carga_p1_call(pulsador: PulsadorId) -> None:
    global _carga_p1_call_pending
    _carga_p1_call_pending = True
    _carga_cajero_reposo()
    _record(
        "zaguan_carga_cajero_call",
        f"Carga cajero: llamada consola {pulsador} (P1)",
        {"pulsador": pulsador, "mode": _current_mode},
    )


def _clear_carga_p1_call() -> None:
    global _carga_p1_call_pending
    _carga_p1_call_pending = False


def _autoservicio_reposo() -> None:
    """Excel ATM reposo: P1 verde, P2 ext rojo, P1 int y P2 int verde."""
    _stop_all_winhose_intermittent()
    _apply_led_map(dict(INITIAL_LED_BY_MODE["horario_autoservicio"]))


def _cerrado_reposo() -> None:
    """Cerrado reposo: exteriores apagado, interiores libre. WinHose y maniobras usan otros estados."""
    _stop_all_winhose_intermittent()
    _apply_led_map(dict(INITIAL_LED_BY_MODE["horario_cerrado"]))


def _mode_reposo() -> None:
    if _current_mode == "horario_autoservicio":
        _autoservicio_reposo()
    elif _current_mode == "horario_carga_cajero":
        _carga_cajero_reposo()
    elif _current_mode == "horario_manual":
        _apply_led_map(dict(INITIAL_LED_BY_MODE["horario_manual"]))
    elif _current_mode == "horario_cerrado":
        _cerrado_reposo()


async def _winhose_window_timer(door: PuertaId, until: float) -> None:
    """Mantiene la ventana WinHose hasta expiración (LEDs en parpadeo vía config)."""
    try:
        delay = until - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        pass
    finally:
        if _current_mode != "horario_cerrado" or _winhose_window_active_for(door):
            return
        if (
            _door_interlock_active.get("p1")
            or _door_interlock_active.get("p2")
            or _pending_abriendo.get("p1")
            or _pending_abriendo.get("p2")
        ):
            return
        try:
            await asyncio.to_thread(_cerrado_reposo)
        except Exception as e:  # noqa: BLE001
            log.debug("Reposo cerrado tras ventana WinHose: %s", e)


def _apply_winhose_window_leds(door: PuertaId) -> None:
    """LEDs libre durante ventana WinHose (animación parpadeo en el dispositivo)."""
    if _current_mode == "horario_autoservicio":
        _apply_led_map(
            {"p1": "libre", "p2": "libre", "p3": "libre", "p4": "libre"}
        )
    elif _current_mode == "horario_cerrado":
        ch = EXTERIOR_PULSADOR[door]
        with _led_state_lock:
            _led_states[ch] = "libre"
            _sync_led_memory()
        _publish_zaguan_led_state()
        _schedule_led_device_push({ch: "libre"})


def _start_winhose_window(door: PuertaId) -> None:
    """Flanco ON→OFF en llave WinHose → ventana 15 s con libre en parpadeo."""
    until = time.monotonic() + WINHOSE_WINDOW_SECONDS
    _winhose_window_until[door] = until
    _stop_winhose_intermittent(door)
    _apply_winhose_window_leds(door)
    _record(
        "zaguan_winhose_window",
        f"Ventana WinHose {door} ({WINHOSE_WINDOW_SECONDS}s)",
        {
            "door": door,
            "until_s": WINHOSE_WINDOW_SECONDS,
            "input": WINHOSE_INPUT_BY_DOOR[door],
            "mode": _current_mode,
        },
    )
    log.info(
        "WinHose %s: ventana %ss — libre parpadeo",
        door,
        WINHOSE_WINDOW_SECONDS,
    )
    _winhose_intermittent_tasks[door] = _schedule_coro(
        _winhose_window_timer(door, until)
    )


def trigger_winhose_window(door: PuertaId) -> tuple[bool, str]:
    """Abre ventana WinHose 15 s (p. ej. emulación llave). Ignora grace de cambio de modo."""
    if _current_mode not in WINHOSE_MODES:
        return False, f"Modo {_current_mode!r} sin WinHose"
    if door not in _winhose_doors_for_mode(_current_mode):
        return False, f"WinHose de {door} no aplica en {_current_mode}"
    code = WINHOSE_INPUT_BY_DOOR[door]
    _winhose_last_closed[code] = True
    _start_winhose_window(door)
    _winhose_last_closed[code] = False
    if not _winhose_window_active_for(door):
        return False, "Ventana WinHose no arrancó"
    if _winhose_intermittent_tasks.get(door) is None:
        return False, "Ventana WinHose no programada (reinicia backend)"
    return True, ""


def _sync_winhose_expirations() -> None:
    """Al expirar ventanas WinHose, restaurar reposo si no hay maniobra en curso."""
    if _current_mode not in WINHOSE_MODES:
        return
    expired_any = False
    for door in _winhose_doors_for_mode(_current_mode):
        if _winhose_window_until.get(door, 0.0) <= 0:
            continue
        if _winhose_window_active_for(door):
            continue
        _winhose_window_until[door] = 0.0
        _stop_winhose_intermittent(door)
        expired_any = True
        _record(
            "zaguan_winhose_expired",
            f"Ventana WinHose {door} expirada",
            {"door": door, "mode": _current_mode},
        )
    if not expired_any:
        return
    if _door_interlock_active.get("p1") or _door_interlock_active.get("p2"):
        if _current_mode == "horario_autoservicio":
            _sync_autoservicio_interlock_leds()
        elif _current_mode == "horario_cerrado":
            _sync_cerrado_interlock_leds()
        return
    if _any_winhose_window_active():
        for wh_door in _winhose_doors_for_mode(_current_mode):
            if _winhose_window_active_for(wh_door):
                _apply_winhose_window_leds(wh_door)
        return
    _mode_reposo()


def poll_winhose() -> None:
    """
    WinHose: cerrado=ON, abierto=OFF. Flanco ON→OFF → ventana 15 s por puerta.
    Autoservicio: solo P2 (IN_03_03). Cerrado: P1 (IN_02_03) y P2 (IN_03_03).
    """
    if not ORCHESTRATOR_ENABLED or _current_mode not in WINHOSE_MODES:
        return

    in_grace = (time.monotonic() - _winhose_mode_changed_at) < WINHOSE_EDGE_GRACE_S

    for door in _winhose_doors_for_mode(_current_mode):
        code = WINHOSE_INPUT_BY_DOOR[door]
        try:
            closed = _read_input(code)
        except Exception as e:  # noqa: BLE001
            log.debug("WinHose lectura %s: %s", code, e)
            continue

        last = _winhose_last_closed.get(code)
        if last is None:
            _winhose_last_closed[code] = closed
            continue

        if not in_grace and last and not closed:
            log.info("WinHose: flanco cerrado→abierto en %s (%s)", code, door)
            _start_winhose_window(door)

        _winhose_last_closed[code] = closed

    _sync_winhose_expirations()


def _zaguan_occupied() -> bool:
    """True si IN_02_10 o IN_03_10 detectan presencia en el zaguán."""
    for code in OCCUPANCY_INPUT_CODES:
        try:
            if _read_input(code):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _exterior_entry_blocked_by_presence(pulsador: PulsadorId) -> tuple[bool, str]:
    """Bloqueo por presencia física: solo entradas exteriores P1/P2 en modos con sensor."""
    if _current_mode not in ZAGUAN_OCCUPANCY_MODES:
        return False, ""
    if pulsador not in ("p1", "p2"):
        return False, ""
    if not _zaguan_occupied():
        return False, ""
    return True, "Zaguán ocupado (IN_02_10 / IN_03_10)"


def _door_is_open(door: PuertaId) -> bool:
    code = DOOR_OPEN_SENSOR[door]
    try:
        return _read_input(code)
    except Exception:  # noqa: BLE001
        return False


def _sync_door_was_open_baseline(door: PuertaId) -> None:
    """Alinea memoria del sensor con hardware al iniciar apertura (evita flancos falsos)."""
    _door_was_open[door] = _door_is_open(door)


def _suppress_tablet_close_edge(door: PuertaId, *, age_s: float) -> bool:
    """
    Manual/carga: no tratar cierre por sensor si la maniobra acaba de empezar
    o el inductivo aún no confirmó apertura en este ciclo.
    """
    if _current_mode not in TABLET_LOCK_RELEASE_MODES or not _pending_abriendo.get(door):
        return False
    if age_s < DOOR_AUTOSERVICIO_MIN_MANEUVER_S:
        return True
    return not _saw_open_during_pending.get(door)


def _p2_blocks_p1_autoservicio() -> bool:
    return bool(
        _door_interlock_active.get("p2")
        or _pending_abriendo.get("p2")
        or _door_is_open("p2")
    )


def _p1_blocks_p2_autoservicio() -> bool:
    return bool(
        _door_interlock_active.get("p1")
        or _pending_abriendo.get("p1")
        or _door_is_open("p1")
    )


def _can_open_p1_autoservicio(pulsador: PulsadorId) -> tuple[bool, str]:
    blocked, reason = _exterior_entry_blocked_by_presence(pulsador)
    if blocked:
        return False, f"Autoservicio: {reason}"
    if _p2_blocks_p1_autoservicio():
        return False, "Autoservicio: P2 debe estar totalmente cerrada"
    return True, ""


def _can_open_p2_autoservicio(pulsador: PulsadorId) -> tuple[bool, str]:
    blocked, reason = _exterior_entry_blocked_by_presence(pulsador)
    if blocked:
        return False, f"Autoservicio: {reason}"
    if _p1_blocks_p2_autoservicio():
        return False, "Autoservicio: P1 debe estar totalmente cerrada"
    if pulsador == "p2" and not _winhose_window_active_for("p2"):
        return False, "Autoservicio: P2 exterior solo tras maniobra WinHose (15 s)"
    return True, ""


def _can_open_cerrado(pulsador: PulsadorId) -> tuple[bool, str]:
    door = PULSADOR_TO_DOOR[pulsador]
    if pulsador in ("p1", "p2") and not _winhose_window_active_for(door):
        return False, f"Cerrado: {door} exterior solo tras maniobra WinHose (15 s)"
    ok, reason = _can_open_in_interlock(door)
    if not ok:
        return False, f"Cerrado: {reason}"
    return True, ""


def _cerrado_exterior_uses_direct_pulse(pulsador: PulsadorId) -> bool:
    """
    En cerrado, interfono exterior tiene blocked_if_active IN_01_05 (el propio modo).
    El orquestador ya validó WinHose → pulso directo (apertura + cierres mecánicos).
    """
    return _current_mode == "horario_cerrado" and pulsador in ("p1", "p2")


def _output_is_on(out_code: str) -> bool:
    panel = _import_panel()
    board_id, channel = panel._parse_out_code(out_code)  # noqa: SLF001
    return bool(panel._read_output_cached(board_id, channel))  # noqa: SLF001


def _set_output_direct(out_code: str, on: bool) -> None:
    """Escribe salida Modbus sin pasar por el hook de apertura tablet."""
    panel = _import_panel()
    board_id, channel = panel._parse_out_code(out_code)  # noqa: SLF001
    if not panel.io_state.get(board_id, {}).get("connected"):
        panel._connect_board(board_id)  # noqa: SLF001
    panel._write_output(board_id, channel, on)  # noqa: SLF001


def _notify_panel_outputs_written(out_codes: list[str], *, on: bool) -> None:
    """
    Empuja el estado al WS del panel/COCE.

    `_write_output` actualiza io_state en RAM; el siguiente poll Modbus no ve
    delta y el dashboard no refresca hasta recargar.
    """
    codes = [c for c in (out_codes or []) if c]
    if not codes:
        return
    try:
        panel = _import_panel()
        for code in codes:
            try:
                board_id, channel = panel._parse_out_code(code)  # noqa: SLF001
            except Exception:  # noqa: BLE001
                continue
            panel._coce_notify(  # noqa: SLF001
                "output_changed",
                {
                    "board_id": board_id,
                    "channel": channel,
                    "state": on,
                    "code": code,
                },
            )
        panel._publish_panel_status_debounced(force=True)  # noqa: SLF001
    except Exception as e:  # noqa: BLE001
        log.debug("No se pudo notificar salidas por WS: %s", e)


def _door_for_open_output(code: str) -> Optional[PuertaId]:
    for door, out_code in DOOR_OPEN_OUTPUT.items():
        if out_code == code:
            return door
    return None


def door_for_hold_output(code: str) -> Optional[PuertaId]:
    """OUT_xx_07 de mantenimiento de apertura (tablet / cola de modos)."""
    return _door_for_open_output(code)


def door_hold_output_for_sensor(sensor_code: str) -> Optional[str]:
    """IN_02_04 / IN_03_04 → OUT_02_07 / OUT_03_07."""
    for door, in_code in DOOR_OPEN_SENSOR.items():
        if in_code == sensor_code:
            return DOOR_OPEN_OUTPUT[door]
    return None


def on_tablet_hold_output_released(door: PuertaId) -> None:
    """Tablet apagó OUT_xx_07 para liberar bloqueo de puerta (p. ej. cola de modo)."""
    if _current_mode not in TABLET_LOCK_RELEASE_MODES:
        return
    _refresh_board_for_door(door)
    if not _door_is_open(door):
        _on_door_closed(door, source="tablet_hold_off")


def prepare_closed_mode_transition(
    *,
    bolt_settle_s: Optional[float] = None,
    timeout_s: Optional[float] = None,
) -> dict[str, Any]:
    """
    Fuerza cierre de P1/P2, espera sensores de puerta cerrada, settle de bulones y los activa.
    Usado al entrar a horario_cerrado para no encolar el modo con puertas abiertas.
    """
    settle = float(bolt_settle_s if bolt_settle_s is not None else CLOSED_MODE_BOLT_SETTLE_S)
    timeout = float(timeout_s if timeout_s is not None else CLOSED_MODE_DOOR_CLOSE_TIMEOUT_S)
    try:
        from app.core.config import settings

        settle = float(getattr(settings, "panel_temp_deactivate_restore_delay_seconds", settle) or settle)
    except Exception:  # noqa: BLE001
        pass

    open_before: dict[str, bool] = {}
    for door in ("p1", "p2"):
        try:
            _refresh_board_for_door(door)
        except Exception:  # noqa: BLE001
            pass
        is_open = _door_is_open(door)
        open_before[door] = is_open
        # Asegurar que la salida de apertura no quede forzada ON (hold tablet / pulso).
        try:
            _set_output_direct(DOOR_OPEN_OUTPUT[door], False)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo apagar salida apertura %s: %s", door, e)

    deadline = time.monotonic() + max(1.0, timeout)
    still_open: list[str] = []
    while time.monotonic() < deadline:
        still_open = []
        for door in ("p1", "p2"):
            try:
                _refresh_board_for_door(door)
            except Exception:  # noqa: BLE001
                pass
            if _door_is_open(door):
                still_open.append(door)
        if not still_open:
            break
        time.sleep(CLOSED_MODE_DOOR_POLL_S)

    if still_open:
        log.warning(
            "Transición a cerrado: timeout esperando cierre de %s (antes=%s)",
            still_open,
            open_before,
        )
        return {
            "ok": False,
            "timed_out": True,
            "doors_still_open": still_open,
            "open_before": open_before,
            "bolt_settle_s": settle,
            "reason": f"Puertas aún abiertas tras {timeout:.0f}s: {', '.join(still_open)}",
        }

    if settle > 0:
        log.info("Transición a cerrado: settle bulones %.1fs", settle)
        time.sleep(settle)

    bolts_on: list[str] = []
    for door in ("p1", "p2"):
        for lock_code in DOOR_LOCK_OUTPUTS[door]:
            try:
                _set_output_direct(lock_code, True)
                bolts_on.append(lock_code)
            except Exception as e:  # noqa: BLE001
                log.warning("No se pudo activar bulón %s: %s", lock_code, e)
        _locks_to_restore[door] = []
        _pending_abriendo[door] = False
        _door_was_open[door] = False

    log.info(
        "Transición a cerrado lista (open_before=%s, bulones=%s)",
        open_before,
        bolts_on,
    )
    if bolts_on:
        _notify_panel_outputs_written(bolts_on, on=True)
    return {
        "ok": True,
        "timed_out": False,
        "doors_still_open": [],
        "open_before": open_before,
        "bolts_on": bolts_on,
        "bolt_settle_s": settle,
        "closing_doors": any(open_before.values()),
    }


def _sync_current_mode_from_panel() -> None:
    """Alinea modo orquestador con el panel antes de apertura tablet."""
    mode = _read_panel_mode()
    if mode == _current_mode:
        return
    on_mode_changed(mode)


def _try_tablet_maneuver_close(
    door: PuertaId, *, is_open: bool, age_s: float
) -> bool:
    """
    Manual/carga: cierre por inductivo en OFF tras haber visto apertura.
    No exige flanco was_open→closed (evita retrasos con baseline del sensor).
    """
    if _current_mode not in TABLET_LOCK_RELEASE_MODES:
        return False
    if not _pending_abriendo.get(door):
        return False
    if is_open:
        return False
    if age_s < DOOR_AUTOSERVICIO_MIN_MANEUVER_S:
        return False
    if not _saw_open_during_pending.get(door):
        return False
    _on_door_closed(door, source="tablet_sensor_closed")
    return True


def _tablet_led_reposo_after_s() -> float:
    if _current_mode in TABLET_LOCK_RELEASE_MODES:
        return TABLET_LED_REPOSO_AFTER_S
    return DOOR_LED_REPOSO_AFTER_S


def _validate_tablet_door_open(door: PuertaId) -> tuple[bool, str]:
    """Validación apertura tablet (sin exigir llamada previa)."""
    if _current_mode not in TABLET_LOCK_RELEASE_MODES:
        return False, f"Modo {_current_mode!r} no permite apertura tablet con bulones"
    if _current_mode == "horario_carga_cajero" and door != "p1":
        return False, "Carga cajero: solo P1"
    if _current_mode == "horario_extendido":
        if door == "p2":
            blocked, reason = _exterior_entry_blocked_by_presence("p2")
            if blocked:
                return False, f"Extendido: {reason}"
        elif door == "p1":
            blocked, reason = _exterior_entry_blocked_by_presence("p1")
            if blocked:
                return False, f"Extendido: {reason}"
    return _can_open_in_interlock(door)


def _refresh_board_for_door(door: PuertaId) -> None:
    panel = _import_panel()
    board_id = DOOR_BOARD_ID[door]
    try:
        panel.api_v1_refresh_board_io(board_id)
    except Exception as e:  # noqa: BLE001
        log.debug("Refresh placa %s (puerta %s): %s", board_id, door, e)


def _finalize_tablet_door_open(door: PuertaId, *, source: str) -> None:
    if _current_mode == "horario_carga_cajero":
        _clear_carga_p1_call()
    _set_door_abriendo(door, source=source)


def _release_locks_before_open(door: PuertaId) -> tuple[dict[str, bool], list[str]]:
    """Lee bulones OUT_x_01/02; solo apaga los que están ON y marca cuáles restaurar al cerrar."""
    _cancel_lock_restore(door)
    _refresh_board_for_door(door)
    locks_before: dict[str, bool] = {}
    released: list[str] = []
    for lock_code in DOOR_LOCK_OUTPUTS[door]:
        on = _output_is_on(lock_code)
        locks_before[lock_code] = on
        if on:
            _set_output_direct(lock_code, False)
            released.append(lock_code)
            log.info("Bulones OFF antes apertura %s: %s", door, lock_code)
    _locks_to_restore[door] = released
    return locks_before, released


def _cancel_lock_restore(door: PuertaId) -> None:
    _cancel_scheduled(_lock_restore_tasks.get(door))
    _lock_restore_tasks[door] = None


def _cancel_all_lock_restores() -> None:
    for door in ("p1", "p2"):
        _cancel_lock_restore(door)


def _door_for_lock_output(out_code: str) -> Optional[PuertaId]:
    code = (out_code or "").strip().upper()
    for door, locks in DOOR_LOCK_OUTPUTS.items():
        if code in locks:
            return door
    return None


def is_door_lock_output(out_code: str) -> bool:
    return _door_for_lock_output(out_code) is not None


def _lock_restore_delay_s() -> float:
    """Retardo tras IN4 OFF antes de echar bulones (más largo en oficina cerrada)."""
    delay = float(DOOR_LOCK_RESTORE_DELAY_S)
    if _current_mode == "horario_cerrado":
        delay = max(delay, float(CLOSED_MODE_BOLT_SETTLE_S))
        try:
            from app.core.config import settings

            cfg = float(
                getattr(settings, "panel_temp_deactivate_restore_delay_seconds", 0) or 0
            )
            if cfg > 0:
                delay = max(delay, cfg)
        except Exception:  # noqa: BLE001
            pass
    return max(0.0, delay)


def _restore_locks_after_close(door: PuertaId) -> None:
    """Vuelve a activar los bulones que se soltaron para abrir desde tablet."""
    pending = _locks_to_restore.get(door) or []
    if not pending:
        return
    # Seguridad: no echar bulones si el sensor sigue marcando abierta.
    try:
        _refresh_board_for_door(door)
        if _door_is_open(door):
            log.info(
                "Bulones %s: IN4 aún activo; se reagenda restauración (%s)",
                door,
                pending,
            )
            _door_was_open[door] = True
            return
    except Exception as e:  # noqa: BLE001
        log.debug("No se pudo verificar sensor antes de bulones %s: %s", door, e)
    for lock_code in pending:
        _set_output_direct(lock_code, True)
        log.info("Bulones ON tras cierre %s: %s", door, lock_code)
    _locks_to_restore[door] = []
    _notify_panel_outputs_written(pending, on=True)


async def _delayed_restore_locks(door: PuertaId, delay_s: float) -> None:
    """Espera delay_s tras cierre confirmado y luego activa bulones."""
    try:
        await asyncio.sleep(delay_s)
        if _current_mode not in (
            "horario_cerrado",
            *TABLET_LOCK_RELEASE_MODES,
        ):
            # Fuera de modos con cierres activos: no forzar bulones ON.
            _locks_to_restore[door] = []
            return
        if not (_locks_to_restore.get(door) or []):
            return
        # Si la puerta se reabrió durante el settle, no echar bulones; esperar nuevo cierre.
        still_open = await asyncio.to_thread(_door_is_open, door)
        if still_open:
            log.info(
                "Bulones %s: puerta reabierta durante settle; se espera nuevo cierre",
                door,
            )
            _door_was_open[door] = True
            return
        await asyncio.to_thread(_restore_locks_after_close, door)
    except asyncio.CancelledError:
        return
    except Exception as e:  # noqa: BLE001
        log.warning("Error restaurando bulones %s tras retardo: %s", door, e)
    finally:
        if _lock_restore_tasks.get(door) is not None:
            _lock_restore_tasks[door] = None


def _schedule_lock_restore_after_close(door: PuertaId) -> None:
    """Programa restauración de bulones con retardo tras cierre (cerrado / manual / carga / extendido)."""
    if not (_locks_to_restore.get(door) or []):
        return
    _cancel_lock_restore(door)
    delay = _lock_restore_delay_s()
    log.info(
        "Bulones %s: restauración en %.1fs tras cierre (modo=%s)",
        door,
        delay,
        _current_mode,
    )
    _lock_restore_tasks[door] = _schedule_coro(_delayed_restore_locks(door, delay))


def defer_lock_outputs_until_door_settled(out_codes: list[str]) -> list[str]:
    """
    No echa bulones (OUT_x_01/02) mientras IN4 marque puerta abierta.
    Cuando el sensor se apague, espera settle y entonces restaura.
    Devuelve los códigos de bulón que se diferieron.
    """
    deferred: list[str] = []
    by_door: dict[PuertaId, list[str]] = {"p1": [], "p2": []}
    for raw in out_codes:
        code = (raw or "").strip().upper()
        door = _door_for_lock_output(code)
        if not door:
            continue
        by_door[door].append(code)
        deferred.append(code)

    for door, codes in by_door.items():
        if not codes:
            continue
        _cancel_lock_restore(door)
        merged = list(dict.fromkeys((_locks_to_restore.get(door) or []) + codes))
        _locks_to_restore[door] = merged
        try:
            _refresh_board_for_door(door)
        except Exception:  # noqa: BLE001
            pass
        if _door_is_open(door):
            # Asegurar flanco de cierre en el poll de sensores.
            _door_was_open[door] = True
            log.info(
                "Bulones %s diferidos hasta IN4 OFF + settle: %s",
                door,
                codes,
            )
        else:
            log.info(
                "Bulones %s: puerta ya cerrada; settle antes de ON: %s",
                door,
                codes,
            )
            _schedule_lock_restore_after_close(door)
    return deferred


def _door_pulse_with_locks_sync(door: PuertaId, *, restore_locks: bool) -> None:
    """Libera bulones, pulsa apertura; por defecto restaura bulones solo al cerrar puerta."""
    open_code = DOOR_OPEN_OUTPUT[door]
    _, released = _release_locks_before_open(door)
    try:
        _set_output_direct(open_code, True)
        time.sleep(DOOR_INTERFONO_PULSE_SECONDS)
        _set_output_direct(open_code, False)
        if restore_locks:
            _restore_locks_after_close(door)
        elif not released:
            _locks_to_restore[door] = []
    except Exception:
        if released and not restore_locks:
            for lock_code in released:
                _set_output_direct(lock_code, True)
            _locks_to_restore[door] = []
        raise


def open_door_from_tablet(door: PuertaId) -> dict[str, Any]:
    """
    Apertura explícita desde tablet (POST /api/v1/door/open).
    Comprueba OUT_x_01/02, apaga solo los activos, pulsa apertura y restaura bulones al cerrar.
    """
    _sync_current_mode_from_panel()
    ok, reason = _validate_tablet_door_open(door)
    if not ok:
        return {"ok": False, "executed": False, "door": door, "reason": reason}

    locks_before, locks_released = _release_locks_before_open(door)
    _sync_door_was_open_baseline(door)
    # LEDs e interlock antes del pulso Modbus (no esperar 2 s ni al sensor).
    _finalize_tablet_door_open(door, source="tablet:door/open")
    open_code = DOOR_OPEN_OUTPUT[door]
    try:
        _set_output_direct(open_code, True)
        time.sleep(DOOR_INTERFONO_PULSE_SECONDS)
        _set_output_direct(open_code, False)
    except Exception as e:  # noqa: BLE001
        for lock_code in locks_released:
            _set_output_direct(lock_code, True)
        _locks_to_restore[door] = []
        _pending_abriendo[door] = False
        _abriendo_since[door] = 0.0
        _saw_open_during_pending[door] = False
        if _current_mode == "horario_manual":
            _apply_led_map(
                dict(INITIAL_LED_BY_MODE["horario_manual"]),
                priority_door=door,
            )
        elif _current_mode == "horario_carga_cajero":
            _carga_cajero_reposo()
        log.warning("Error apertura tablet puerta %s: %s", door, e)
        return {"ok": False, "executed": False, "door": door, "reason": str(e)}

    log.info(
        "Apertura tablet puerta %s (modo=%s, bulones liberados=%s)",
        door,
        _current_mode,
        locks_released,
    )
    return {
        "ok": True,
        "executed": True,
        "door": door,
        "mode": _current_mode,
        "locks_before": locks_before,
        "locks_released": locks_released,
        "open_output": open_code,
        "pulse_seconds": DOOR_INTERFONO_PULSE_SECONDS,
        "locks_restore_on_close": bool(locks_released),
        "leds": get_led_states(),
    }


async def _door_pulse_with_locks(door: PuertaId, *, restore_locks: bool) -> None:
    """Replica interfono: libera cierres, pulsa apertura; restaura al cerrar salvo restore_locks."""
    await asyncio.to_thread(_door_pulse_with_locks_sync, door, restore_locks=restore_locks)


async def _execute_cerrado_exterior_pulse(door: PuertaId) -> dict[str, Any]:
    await _door_pulse_with_locks(door, restore_locks=False)
    return {
        "executed": True,
        "direct_output": DOOR_OPEN_OUTPUT[door],
        "locks_released": list(_locks_to_restore.get(door) or []),
        "pulse_seconds": DOOR_INTERFONO_PULSE_SECONDS,
        "locks_restore_on_close": True,
        "reason": "cerrado_exterior_winhose",
    }


def execute_tablet_door_open_sync(rule_key: str) -> Optional[dict[str, Any]]:
    """Compat: set_rule interfono → misma lógica que POST /door/open."""
    if _current_mode not in TABLET_LOCK_RELEASE_MODES:
        return None
    if not rule_key.startswith("interfono_puerta_"):
        return None
    door = _rule_opens_door(rule_key)
    if not door:
        return None
    result = open_door_from_tablet(door)
    if not result.get("ok"):
        return {"executed": False, "rule": rule_key, **result}
    return {"rule": rule_key, **result}


def execute_tablet_door_output_sync(code: str, on: bool) -> Optional[dict[str, Any]]:
    """Compat: set_output OUT_x_07 → misma lógica que POST /door/open."""
    if _current_mode not in TABLET_LOCK_RELEASE_MODES:
        return None
    door = _door_for_open_output(code)
    if not door or not on:
        return None
    result = open_door_from_tablet(door)
    if not result.get("ok"):
        return {"executed": False, "code": code, "on": on, **result}
    panel = _import_panel()
    board_id, channel = panel._parse_out_code(code)  # noqa: SLF001
    return {"code": code, "on": on, "board_id": board_id, "channel": channel, **result}


def _opposite_door_blocks(door: PuertaId) -> bool:
    other = OPPOSITE_DOOR[door]
    return bool(_pending_abriendo.get(other) or _door_is_open(other))


def _can_open_in_interlock(door: PuertaId) -> tuple[bool, str]:
    # Carga cajero: P2 queda en servicio/abierta; P1 se autoriza sin exigir P2 cerrada.
    if _current_mode == "horario_carga_cajero" and door == "p1":
        return True, ""
    if _opposite_door_blocks(door):
        other = OPPOSITE_DOOR[door]
        return False, f"Puerta {other} debe estar totalmente cerrada"
    return True, ""


def _can_open_in_esclusa(door: PuertaId) -> tuple[bool, str]:
    ok, reason = _can_open_in_interlock(door)
    if not ok:
        return False, f"Esclusa: {reason}"
    return True, ""


def _can_open_p1_extendido(pulsador: PulsadorId) -> tuple[bool, str]:
    blocked, reason = _exterior_entry_blocked_by_presence(pulsador)
    if blocked:
        return False, reason
    ok, reason = _can_open_in_interlock("p1")
    if not ok:
        return False, f"Extendido: {reason}"
    return True, ""


def _esclusa_active_door() -> Optional[PuertaId]:
    """Puerta con maniobra en curso o físicamente abierta (IN_xx_04)."""
    if _pending_abriendo.get("p1") or _door_is_open("p1"):
        return "p1"
    if _pending_abriendo.get("p2") or _door_is_open("p2"):
        return "p2"
    return None


def _esclusa_led_states_for(door: PuertaId) -> dict[PulsadorId, EstadoLed]:
    other = OPPOSITE_DOOR[door]
    states: dict[PulsadorId, EstadoLed] = {}
    for ch in DOOR_TO_LED_CHANNELS[door]:
        states[ch] = "abriendo"
    for ch in DOOR_TO_LED_CHANNELS[other]:
        states[ch] = "ocupado"
    return states


def _apply_esclusa_led_for_door(door: PuertaId) -> None:
    _apply_led_map(_esclusa_led_states_for(door), priority_door=door)


def _sync_manual_interlock_leds() -> None:
    """Manual: reposo 4× libre; interlock solo mientras _pending_abriendo (no re-pisar por sensor)."""
    if _current_mode != "horario_manual":
        return
    for door in ("p1", "p2"):
        if _pending_abriendo.get(door):
            expected = _esclusa_led_states_for(door)
            if _led_states_match(expected):
                return
            _apply_esclusa_led_for_door(door)
            return
    target = dict(INITIAL_LED_BY_MODE["horario_manual"])
    if _led_states_match(target):
        return
    _apply_led_map(target)


def _sync_interlock_leds() -> None:
    """Esclusa/extendido: reposo (4× libre) solo cuando ambas puertas están cerradas."""
    if _current_mode not in INTERLOCK_MODES:
        return
    if (
        EXTENDIDO_TABLET_CALL_ENABLED
        and _current_mode == "horario_extendido"
        and _extendido_p2_call_pending
    ):
        return
    active = _esclusa_active_door()
    if active is None:
        initial = INITIAL_LED_BY_MODE.get(_current_mode)
        if initial:
            _apply_led_map(dict(initial))
    else:
        _apply_esclusa_led_for_door(active)


def _sync_esclusa_leds() -> None:
    _sync_interlock_leds()


def _sync_autoservicio_interlock_leds() -> None:
    """Interbloqueo activo: par de la puerta en maniobra, opuesto ocupado."""
    if _p2_blocks_p1_autoservicio():
        _apply_led_map(
            {
                "p1": "ocupado",
                "p3": "ocupado",
                "p2": "abriendo",
                "p4": "abriendo",
            }
        )
    elif _p1_blocks_p2_autoservicio():
        _apply_led_map(
            {
                "p1": "abriendo",
                "p3": "abriendo",
                "p2": "ocupado",
                "p4": "ocupado",
            }
        )


def _sync_cerrado_interlock_leds() -> None:
    """Interbloqueo cerrado: par activo abriendo, opuesto ocupado."""
    if _p2_blocks_p1_autoservicio():
        _apply_led_map(
            {
                "p1": "ocupado",
                "p3": "ocupado",
                "p2": "abriendo",
                "p4": "abriendo",
            }
        )
    elif _p1_blocks_p2_autoservicio():
        _apply_led_map(
            {
                "p1": "abriendo",
                "p3": "abriendo",
                "p2": "ocupado",
                "p4": "ocupado",
            }
        )


def _apply_strict_interlock_abriendo(door: PuertaId) -> None:
    _apply_led_map(_esclusa_led_states_for(door), priority_door=door)


def on_mode_changed(mode: Optional[str]) -> None:
    if not ORCHESTRATOR_ENABLED:
        return
    global _current_mode, _winhose_mode_changed_at
    _current_mode = mode
    _winhose_mode_changed_at = time.monotonic()
    _pending_abriendo["p1"] = False
    _pending_abriendo["p2"] = False
    _abriendo_since["p1"] = 0.0
    _abriendo_since["p2"] = 0.0
    _saw_open_during_pending["p1"] = False
    _saw_open_during_pending["p2"] = False
    _door_interlock_active["p1"] = False
    _door_interlock_active["p2"] = False
    _saw_open_while_interlock["p1"] = False
    _saw_open_while_interlock["p2"] = False
    _door_closed_streak["p1"] = 0
    _door_closed_streak["p2"] = 0
    _reset_winhose_state()
    _reset_extendido_state()
    _reset_carga_state()
    _cancel_all_lock_restores()
    _locks_to_restore["p1"] = []
    _locks_to_restore["p2"] = []

    if mode not in SUPPORTED_MODES:
        log.info("Modo %s sin orquestación LED zaguán", mode)
        return

    initial = INITIAL_LED_BY_MODE.get(mode)
    if not initial:
        return
    _apply_led_map(initial)
    if mode in WINHOSE_MODES:
        _seed_winhose_baseline()
    _record(
        "zaguan_mode_led_init",
        f"LED inicial modo {mode}",
        {"mode": mode, "leds": dict(_led_states)},
    )
    log.info("Zaguán LED inicial modo %s: %s", mode, _led_states)


def on_rule_executed(rule_key: str, result: dict[str, Any]) -> None:
    if not ORCHESTRATOR_ENABLED or not result.get("executed"):
        return
    if _current_mode not in SUPPORTED_MODES:
        return
    if not any(rule_key.startswith(p) for p in DOOR_OPEN_RULE_PREFIXES):
        return

    door = _rule_opens_door(rule_key)
    if not door:
        return

    if _current_mode == "horario_autoservicio":
        if door == "p2":
            return
        pulsador_hint: PulsadorId = "p3" if "interior" in rule_key else "p1"
        ok, _ = _can_open_p1_autoservicio(pulsador_hint)
        if not ok:
            return
    elif _current_mode == "horario_esclusa":
        ok, _ = _can_open_in_esclusa(door)
        if not ok:
            return
    elif _current_mode == "horario_extendido":
        if door == "p1":
            pulsador_hint = "p3" if "interior" in rule_key else "p1"
            ok, _ = _can_open_p1_extendido(pulsador_hint)
            if not ok:
                return
        elif door == "p2" and "interior" not in rule_key:
            blocked, _ = _exterior_entry_blocked_by_presence("p2")
            if blocked:
                return
        ok, _ = _can_open_in_interlock(door)
        if not ok:
            return
        if EXTENDIDO_TABLET_CALL_ENABLED and door == "p2":
            _clear_extendido_p2_call()
    elif _current_mode == "horario_carga_cajero":
        if door != "p1":
            return
        ok, reason = _can_open_in_interlock("p1")
        if not ok:
            log.info("Carga cajero: apertura P1 bloqueada: %s", reason)
            return
        _clear_carga_p1_call()
    elif _current_mode == "horario_manual":
        ok, reason = _can_open_in_interlock(door)
        if not ok:
            log.info("Manual: apertura %s bloqueada: %s", door, reason)
            return
    elif _current_mode == "horario_cerrado":
        ok, _ = _can_open_in_interlock(door)
        if not ok:
            return

    _set_door_abriendo(door, source=f"rule:{rule_key}")


def _set_door_abriendo(door: PuertaId, *, source: str) -> None:
    _pending_abriendo[door] = True
    _abriendo_since[door] = time.monotonic()
    _saw_open_during_pending[door] = _door_is_open(door)
    if _current_mode in STRICT_INTERLOCK_MODES:
        _door_interlock_active[door] = True
        _clear_winhose_window(door)
        _apply_strict_interlock_abriendo(door)
    elif _current_mode in INTERLOCK_MODES:
        if (
            EXTENDIDO_TABLET_CALL_ENABLED
            and door == "p2"
            and _current_mode == "horario_extendido"
        ):
            _clear_extendido_p2_call()
        _apply_esclusa_led_for_door(door)
    elif _current_mode == "horario_manual":
        _apply_esclusa_led_for_door(door)
    else:
        _apply_led_channels(DOOR_TO_LED_CHANNELS[door], "abriendo")

    _record(
        "zaguan_led_abriendo",
        f"Puerta {door} abriendo ({source})",
        {"door": door, "source": source, "leds": dict(_led_states)},
    )


def _autoservicio_post_close_p1() -> None:
    """Tras cerrar P1: LEDs de reposo (p1/p3 libre; Excel no deja P1 en ocupado)."""
    _autoservicio_reposo()


def _automatico_post_close(door: PuertaId) -> None:
    if door == "p1":
        _apply_led_channels(DOOR_TO_LED_CHANNELS["p1"], "libre")
    else:
        _apply_led_map(INITIAL_LED_BY_MODE["horario_automatico"])


def _try_autoservicio_close_confirm(
    door: PuertaId, *, is_open: bool, was_open: bool, age_s: float
) -> None:
    """Confirma cierre P1/P2 en autoservicio (sensor vio abierta o fallback sin apertura)."""
    if is_open:
        _saw_open_while_interlock[door] = True
        _door_closed_streak[door] = 0
        return

    if (
        was_open
        and _saw_open_while_interlock.get(door)
        and age_s >= DOOR_AUTOSERVICIO_MIN_MANEUVER_S
    ):
        _on_door_closed(door, source="sensor_edge")
        return

    _door_closed_streak[door] += 1
    if age_s < DOOR_AUTOSERVICIO_MIN_MANEUVER_S:
        return
    if _door_closed_streak[door] < DOOR_AUTOSERVICIO_CLOSE_DEBOUNCE_POLLS:
        return

    if _saw_open_while_interlock.get(door):
        _on_door_closed(door, source="sensor_confirmed")
    elif age_s >= DOOR_AUTOSERVICIO_FALLBACK_CLOSE_S:
        _on_door_closed(door, source="fallback_closed")


def _release_autoservicio_door(door: PuertaId) -> None:
    _door_interlock_active[door] = False
    _pending_abriendo[door] = False
    _abriendo_since[door] = 0.0
    _saw_open_while_interlock[door] = False
    _door_closed_streak[door] = 0


def _strict_interlock_post_close(door: PuertaId) -> None:
    if _current_mode == "horario_autoservicio":
        if door == "p1":
            _autoservicio_post_close_p1()
        elif _p2_blocks_p1_autoservicio():
            _sync_autoservicio_interlock_leds()
        else:
            _autoservicio_reposo()
    elif _current_mode == "horario_cerrado":
        if _p2_blocks_p1_autoservicio() or _p1_blocks_p2_autoservicio():
            _sync_cerrado_interlock_leds()
        else:
            _cerrado_reposo()


def _on_door_closed(door: PuertaId, *, source: str = "sensor") -> None:
    pending_locks = bool(_locks_to_restore.get(door))
    if _current_mode in STRICT_INTERLOCK_MODES:
        has_maneuver = bool(
            _door_interlock_active.get(door) or _pending_abriendo.get(door)
        )
        if not has_maneuver and not pending_locks:
            return
        if has_maneuver:
            _release_autoservicio_door(door)
            _strict_interlock_post_close(door)
        elif pending_locks and _current_mode == "horario_cerrado":
            # Emergencia/OFF con bulones diferidos: volver LEDs a reposo cerrado.
            try:
                _cerrado_reposo()
            except Exception:  # noqa: BLE001
                pass
        if _current_mode == "horario_cerrado" and (has_maneuver or pending_locks):
            _schedule_lock_restore_after_close(door)
        _record(
            "zaguan_door_closed",
            f"Puerta {door} cerrada — LED actualizado ({source})",
            {"door": door, "mode": _current_mode, "source": source, "leds": dict(_led_states)},
        )
        log.info("Puerta %s → LED reposo (%s)", door, source)
        return

    if not _pending_abriendo.get(door):
        # Bulones diferidos (p. ej. tras soltar emergencia) sin maniobra LED pendiente.
        if pending_locks and _current_mode in TABLET_LOCK_RELEASE_MODES:
            _schedule_lock_restore_after_close(door)
            log.info("Puerta %s cerrada — bulones diferidos programados (%s)", door, source)
        return
    _pending_abriendo[door] = False
    _abriendo_since[door] = 0.0
    _saw_open_during_pending[door] = False

    if _current_mode == "horario_automatico":
        _automatico_post_close(door)
    elif _current_mode in INTERLOCK_MODES:
        _sync_interlock_leds()
    elif _current_mode == "horario_carga_cajero":
        _clear_carga_p1_call()
        _carga_cajero_reposo()
    elif _current_mode == "horario_manual":
        _apply_led_map(
            dict(INITIAL_LED_BY_MODE["horario_manual"]),
            priority_door=door,
        )
    if _current_mode in TABLET_LOCK_RELEASE_MODES:
        _schedule_lock_restore_after_close(door)
    _record(
        "zaguan_door_closed",
        f"Puerta {door} cerrada — LED actualizado ({source})",
        {"door": door, "mode": _current_mode, "source": source, "leds": dict(_led_states)},
    )
    log.info("Puerta %s → LED reposo (%s)", door, source)


def _emit_door_held_alert(door: PuertaId, *, active: bool, held_s: float = 0.0) -> None:
    try:
        from app.coce.notify import emit_coce_event

        emit_coce_event(
            "branch_alert",
            {
                "alert_type": f"door_held_{door}",
                "active": active,
                "door": door,
                "held_seconds": round(held_s, 1),
                "message": (
                    f"Puerta {door.upper()} abierta más de lo esperado ({held_s:.0f}s)."
                    if active
                    else f"Puerta {door.upper()} cerrada; alerta liberada."
                ),
            },
        )
    except Exception as e:  # noqa: BLE001
        log.debug("door_held alert emit failed: %s", e)


def _track_door_held_alerts(door: PuertaId, *, is_open: bool, now: float) -> None:
    threshold = float(CLOSED_MODE_BOLT_SETTLE_S)
    try:
        from app.core.config import settings

        threshold = float(getattr(settings, "door_held_alert_seconds", 90) or 90)
    except Exception:  # noqa: BLE001
        threshold = 90.0
    threshold = max(15.0, threshold)

    if is_open:
        if _door_open_since[door] <= 0:
            _door_open_since[door] = now
        held = now - _door_open_since[door]
        if held >= threshold and not _door_held_alert_active[door]:
            _door_held_alert_active[door] = True
            _emit_door_held_alert(door, active=True, held_s=held)
            _record(
                "door_held",
                f"Puerta {door} abierta {held:.0f}s",
                {"door": door, "held_seconds": held},
            )
    else:
        _door_open_since[door] = 0.0
        if _door_held_alert_active[door]:
            _door_held_alert_active[door] = False
            _emit_door_held_alert(door, active=False)


def poll_door_sensors() -> None:
    if not ORCHESTRATOR_ENABLED or _current_mode not in SUPPORTED_MODES:
        return

    if _current_mode in WINHOSE_MODES:
        poll_winhose()

    now = time.monotonic()
    panel = _import_panel()
    for door, in_code in DOOR_OPEN_SENSOR.items():
        try:
            is_open = panel.api_v1_read_input_by_code(in_code)
        except Exception as e:  # noqa: BLE001
            log.debug("Lectura sensor puerta %s: %s", door, e)
            continue
        was_open = _door_was_open[door]
        age_s = now - _abriendo_since[door] if _abriendo_since[door] > 0 else 0.0

        if _pending_abriendo.get(door) and is_open:
            _saw_open_during_pending[door] = True

        if _try_tablet_maneuver_close(door, is_open=is_open, age_s=age_s):
            pass
        elif _current_mode in STRICT_INTERLOCK_MODES and _door_interlock_active.get(door):
            _try_autoservicio_close_confirm(
                door, is_open=is_open, was_open=was_open, age_s=age_s
            )
            if (
                _door_interlock_active.get(door)
                and not is_open
                and age_s >= DOOR_AUTOSERVICIO_INTERLOCK_MAX_S
            ):
                _on_door_closed(door, source="interlock_timeout")
        elif was_open and not is_open:
            if not _suppress_tablet_close_edge(door, age_s=age_s):
                _on_door_closed(door, source="sensor_edge")
        elif (
            _current_mode not in STRICT_INTERLOCK_MODES
            and _pending_abriendo.get(door)
            and not is_open
            and age_s >= _tablet_led_reposo_after_s()
            and (
                _current_mode not in TABLET_LOCK_RELEASE_MODES
                or _saw_open_during_pending.get(door)
            )
        ):
            # Fallback automático/esclusa: inductivo no marcó apertura; puerta ya cerrada.
            _on_door_closed(door, source="post_pulse")
        _door_was_open[door] = is_open
        _track_door_held_alerts(door, is_open=is_open, now=now)

    if _current_mode in INTERLOCK_MODES:
        _sync_interlock_leds()
    elif _current_mode == "horario_manual":
        _sync_manual_interlock_leds()
    elif _current_mode == "horario_autoservicio":
        _sync_autoservicio_interlock_leds()
    elif _current_mode == "horario_cerrado":
        _sync_cerrado_interlock_leds()


def _pulsador_blocked_by_led(pulsador: PulsadorId) -> bool:
    if _led_states.get(pulsador) != "ocupado":
        return False
    # Autoservicio: p1/p2 en reposo pueden estar en rojo (cierre P2) sin bloquear pulsación.
    if _current_mode == "horario_autoservicio" and pulsador in ("p1", "p2"):
        return False
    return True


def _pulsador_allowed_in_mode(pulsador: PulsadorId) -> tuple[bool, str]:
    if _current_mode not in SUPPORTED_MODES:
        return False, f"Modo {_current_mode!r} sin orquestación zaguán"

    if _pulsador_blocked_by_led(pulsador):
        return False, f"Pulsador {pulsador} bloqueado (LED ocupado)"

    if _current_mode == "horario_autoservicio":
        if pulsador in ("p1", "p3"):
            return _can_open_p1_autoservicio(pulsador)
        if pulsador in ("p2", "p4"):
            return _can_open_p2_autoservicio(pulsador)

    if _current_mode == "horario_esclusa":
        door = PULSADOR_TO_DOOR[pulsador]
        return _can_open_in_esclusa(door)

    if _current_mode == "horario_extendido":
        if pulsador in ("p1", "p3"):
            return _can_open_p1_extendido(pulsador)
        if pulsador == "p2":
            blocked, reason = _exterior_entry_blocked_by_presence(pulsador)
            if blocked:
                return False, f"Extendido: {reason}"
            ok, reason = _can_open_in_interlock("p2")
            return (ok, f"Extendido: {reason}" if reason else "")
        if pulsador == "p4":
            ok, reason = _can_open_in_interlock("p2")
            return (ok, f"Extendido: {reason}" if reason else "")

    if _current_mode == "horario_cerrado":
        return _can_open_cerrado(pulsador)

    if _current_mode == "horario_carga_cajero":
        if pulsador in ("p1", "p3"):
            # Requiere autorización consola; la validación final se hace en on_rule_executed.
            return True, ""
        return False, "Carga cajero: solo P1 exterior/interior generan llamada a consola"
    if _current_mode == "horario_manual":
        # Manual: cualquier pulsador genera llamada; la apertura ocurre desde botón tablet.
        return True, ""

    return True, ""


async def handle_pulsacion(pulsador: PulsadorId, ts: int) -> dict[str, Any]:
    panel_mode = _read_panel_mode()
    log.info(
        "Orquestador pulsación %s (modo=%s, panel=%s, ts=%s)",
        pulsador,
        _current_mode,
        panel_mode,
        ts,
    )

    from app.services import tablet_call_hub

    force_extendido_tablet_call = (
        EXTENDIDO_TABLET_CALL_ENABLED
        and _current_mode == "horario_extendido"
        and pulsador == "p2"
    )
    force_carga_tablet_call = _current_mode == "horario_carga_cajero" and pulsador in (
        "p1",
        "p3",
    )
    force_manual_tablet_call = _current_mode == "horario_manual" and pulsador in (
        "p1",
        "p2",
        "p3",
        "p4",
    )
    if force_extendido_tablet_call or force_carga_tablet_call or force_manual_tablet_call:
        door = PULSADOR_TO_DOOR[pulsador]
        call_result = await tablet_call_hub.start_call(
            door=door,
            pulsador=pulsador,
            mode=panel_mode or _current_mode or "",
        )
        if force_extendido_tablet_call:
            _start_extendido_p2_call()
        if force_carga_tablet_call:
            _start_carga_p1_call(pulsador)
        # Llamada en curso: LED ocupado en ESP32 + Panphone (p1/p2).
        _apply_led_channels(DOOR_TO_LED_CHANNELS[door], "ocupado")
        _record(
            "zaguan_tablet_call",
            f"Llamada tablet {pulsador} → {door}",
            {
                "pulsador": pulsador,
                "door": door,
                "mode": panel_mode or _current_mode,
                "ts": ts,
                "extendido_call": force_extendido_tablet_call,
                "carga_cajero_call": force_carga_tablet_call,
                "manual_call": force_manual_tablet_call,
                **call_result,
            },
        )
        return {
            "ok": True,
            "pulsador": pulsador,
            "door": door,
            "mode": panel_mode or _current_mode,
            "tablet_call": True,
            "extendido_call": force_extendido_tablet_call,
            "carga_cajero_call": force_carga_tablet_call,
            "manual_call": force_manual_tablet_call,
            "modbus_ok": False,
            "call_id": call_result.get("call_id"),
        }

    if tablet_call_hub.should_start_tablet_call(
        pulsador, panel_mode
    ):
        door = PULSADOR_TO_DOOR[pulsador]
        call_result = await tablet_call_hub.start_call(
            door=door,
            pulsador=pulsador,
            mode=panel_mode or _current_mode or "",
        )
        _apply_led_channels(DOOR_TO_LED_CHANNELS[door], "ocupado")
        _record(
            "zaguan_tablet_call",
            f"Llamada tablet {pulsador} → {door}",
            {
                "pulsador": pulsador,
                "door": door,
                "mode": panel_mode or _current_mode,
                "ts": ts,
                **call_result,
            },
        )
        return {
            "ok": True,
            "pulsador": pulsador,
            "door": door,
            "mode": panel_mode or _current_mode,
            "tablet_call": True,
            "modbus_ok": False,
            "call_id": call_result.get("call_id"),
        }

    allowed, reason = _pulsador_allowed_in_mode(pulsador)
    if not allowed:
        log.info("Pulsación %s rechazada: %s", pulsador, reason)
        _record(
            "zaguan_pulsacion_rejected",
            f"Pulsación {pulsador} rechazada",
            {"pulsador": pulsador, "mode": _current_mode, "reason": reason, "ts": ts},
        )
        return {"ok": False, "reason": reason}

    door = PULSADOR_TO_DOOR[pulsador]
    rule_key = PULSADOR_TO_INTERFONO_RULE[pulsador]

    if _current_mode in WINHOSE_MODES and pulsador in ("p1", "p2"):
        _clear_winhose_window(PULSADOR_TO_DOOR[pulsador])

    if (
        EXTENDIDO_TABLET_CALL_ENABLED
        and _current_mode == "horario_extendido"
        and pulsador == "p4"
    ):
        _clear_extendido_p2_call()

    _set_door_abriendo(door, source=f"pulsacion:{pulsador}")

    modbus_ok = True
    modbus_detail: Any = None
    if MODBUS_ON_PULSACION:
        panel = _import_panel()
        try:
            if _cerrado_exterior_uses_direct_pulse(pulsador):
                modbus_detail = await _execute_cerrado_exterior_pulse(door)
                modbus_ok = True
                log.info(
                    "Pulsación %s cerrado: apertura %s + cierres %s",
                    pulsador,
                    modbus_detail.get("direct_output"),
                    modbus_detail.get("locks_released"),
                )
            else:
                modbus_detail = await asyncio.to_thread(
                    panel.api_v1_execute_rule_for_tablet,
                    rule_key,
                )
                modbus_ok = bool(modbus_detail.get("executed"))
                if not modbus_ok:
                    log.warning(
                        "Regla interfono no ejecutada para %s: %s",
                        pulsador,
                        modbus_detail.get("reason"),
                    )
        except Exception as e:  # noqa: BLE001
            modbus_ok = False
            modbus_detail = str(e)
            log.warning("Error Modbus pulsación %s: %s", pulsador, e)

        if (
            modbus_ok
            and DOOR_PULSE_OFF_SECONDS > 0
            and not _cerrado_exterior_uses_direct_pulse(pulsador)
        ):
            asyncio.create_task(_schedule_door_output_off(door, rule_key, DOOR_PULSE_OFF_SECONDS))

    _record(
        "zaguan_pulsacion",
        f"Pulsación {pulsador} puerta {door}",
        {
            "pulsador": pulsador,
            "door": door,
            "mode": _current_mode,
            "ts": ts,
            "modbus_ok": modbus_ok,
            "rule": rule_key,
            "modbus_detail": modbus_detail if isinstance(modbus_detail, dict) else {"error": modbus_detail},
        },
    )
    return {
        "ok": True,
        "pulsador": pulsador,
        "door": door,
        "mode": _current_mode,
        "modbus_ok": modbus_ok,
    }


async def _schedule_door_output_off(door: PuertaId, rule_key: str, seconds: float) -> None:
    await asyncio.sleep(seconds)
    panel = _import_panel()
    out_code = DOOR_OPEN_OUTPUT[door]
    try:
        await asyncio.to_thread(panel.api_v1_set_output_by_code, out_code, False)
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo apagar %s tras pulso %s: %s", out_code, rule_key, e)


def bootstrap_from_panel() -> None:
    if not ORCHESTRATOR_ENABLED:
        return
    try:
        mode = _import_panel().api_v1_get_current_mode()
    except Exception as e:  # noqa: BLE001
        log.warning("Bootstrap zaguán: %s", e)
        return
    if mode in SUPPORTED_MODES:
        on_mode_changed(mode)
    for door in ("p1", "p2"):
        try:
            is_open = _import_panel().api_v1_read_input_by_code(DOOR_OPEN_SENSOR[door])
            _door_was_open[door] = is_open
        except Exception:  # noqa: BLE001
            pass
    if _current_mode in INTERLOCK_MODES:
        _sync_interlock_leds()
    elif _current_mode == "horario_manual":
        _sync_manual_interlock_leds()
    elif _current_mode in STRICT_INTERLOCK_MODES:
        if _current_mode == "horario_autoservicio":
            _sync_autoservicio_interlock_leds()
        else:
            _sync_cerrado_interlock_leds()
        for code in WINHOSE_INPUT_BY_DOOR.values():
            try:
                _winhose_last_closed[code] = _read_input(code)
            except Exception:  # noqa: BLE001
                pass
