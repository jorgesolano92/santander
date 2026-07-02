"""API compatible con panel ETD8A12 (software prueba_)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from app.db import panel_modules_store as pms
from app.db import system_events_store as ses
from app.db.session import get_connection
from app.core.config import settings
from pydantic import BaseModel
from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ModbusException

router = APIRouter(prefix="/panel")

# Constantes ETD8A12
CMD_OPEN = 0x0100
CMD_CLOSE = 0x0200
CMD_OPEN_ALL = 0x0700
CMD_CLOSE_ALL = 0x0800
REG_OUTPUT_START = 0x0000
REG_OUTPUT_BITS = 0x0070
REG_INPUT_START = 0x0080
REG_IN_OUT_RELATION = 0x00FA  # Típico registro “relación IN/OUT” en ETD8A12; el valor por módulo va en panel_modules.relation_register

# Tipos de regla que participan en el ciclo automático (background / _evaluate_auto_rules).
AUTO_RULE_TYPES = frozenset({"enclavamiento", "pulso_5_sg"})
# `pulse_seconds`: 0 = seguimiento por nivel del trigger (radar); >0 = pulso en segundos (omisión = 0 = detección).
PULSE_5_SG_TYPE = "pulso_5_sg"
PULSE_5_SG_DEFAULT_SECONDS = 0


_coce_status_last_emit: float = 0.0
_COCE_STATUS_MIN_INTERVAL_S = 0.3


def _build_status_payload() -> dict[str, Any]:
    """Misma forma que GET /api/panel/status (estado en RAM, sin releer Modbus)."""
    cfg_map = pms.get_boards_config_map()
    return {
        "boards": {
            str(bid): {
                "id": bid,
                "config": {
                    "name": cfg_map[bid]["name"],
                    "host": cfg_map[bid]["host"],
                    "port": cfg_map[bid]["port"],
                    "slave_id": cfg_map[bid]["slave_id"],
                    "modbus_mode": _modbus_mode(),
                    "serial_port": settings.modbus_serial_port if _is_rtu_mode() else None,
                },
                **io_state.get(bid, {}),
                "input_overrides": input_overrides.get(bid, []),
            }
            for bid in _module_ids()
            if bid in cfg_map
        },
        "modules_config": pms.get_full_config_for_api(),
        "current_mode": current_mode,
        "active_toggle_rules": sorted(active_toggle_rules),
        "pending_manual_enclavamiento_mode": pending_manual_enclavamiento_mode,
        "timestamp": datetime.now().isoformat(),
    }


def _io_tuple(board_id: int) -> tuple[tuple[bool, ...], tuple[bool, ...], tuple[bool, ...]]:
    st = io_state.get(board_id) or {}
    return (
        tuple(st.get("inputs_raw") or []),
        tuple(st.get("inputs") or []),
        tuple(st.get("outputs") or []),
    )


def _publish_panel_status_debounced(*, force: bool = False) -> None:
    """Estado panel en RAM → COCE (WS) y dashboard local (WS)."""
    global _coce_status_last_emit
    now = time.time()
    if not force and now - _coce_status_last_emit < _COCE_STATUS_MIN_INTERVAL_S:
        return
    _coce_status_last_emit = now
    payload = _build_status_payload()
    try:
        from app.coce.notify import emit_coce_event

        emit_coce_event("panel_status", payload)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services import panel_live_hub as plh

        plh.publish_sync({"type": "panel_status", "payload": payload})
    except Exception:  # noqa: BLE001
        pass


def _coce_notify(event_type: str, payload: dict | None = None) -> None:
    try:
        from app.coce.notify import emit_coce_event

        emit_coce_event(event_type, payload or {})
    except Exception:  # noqa: BLE001
        pass
    if event_type == "mode_changed":
        try:
            from app.services import tablet_call_hub

            data = payload or {}
            tablet_call_hub.notify_mode_changed(data.get("current_mode"))
        except Exception:  # noqa: BLE001
            pass
    if event_type != "heartbeat":
        _publish_panel_status_debounced()


def _zaguan_mode_changed(mode: Optional[str]) -> None:
    try:
        from app.services import zaguan_orchestrator as zo

        zo.on_mode_changed(mode)
    except Exception:  # noqa: BLE001
        pass


def _zaguan_rule_executed(rule_key: str, result: dict) -> None:
    if not result.get("executed"):
        return
    try:
        from app.services import zaguan_orchestrator as zo

        zo.on_rule_executed(rule_key, result)
    except Exception:  # noqa: BLE001
        pass


# Modos operativos de consola central (IN1–IN7) + emergencia/incendio (actuación 8, IN9 central).
HORARIO_MODE_KEY_PREFIX = "horario_"
EMERGENCY_MODE_RULE_KEYS = frozenset({"senal_de_incendio_activada"})


def _rule_owns_operational_mode(rule: dict, rule_key: str) -> bool:
    """Solo horarios (IN1–IN7) e incendio/emergencia global actualizan `current_mode`."""
    if (rule.get("type") or "enclavamiento") != "enclavamiento":
        return False
    if rule_key.startswith(HORARIO_MODE_KEY_PREFIX):
        return True
    return rule_key in EMERGENCY_MODE_RULE_KEYS


def _rule_eligible_for_manual_queue(rule_key: str, rule: Optional[dict] = None) -> bool:
    """Modos operativos enclavamiento (horarios / incendio global), no interruptores ni pulso."""
    r = rule if rule is not None else rules_config.get(rule_key) or {}
    return _rule_owns_operational_mode(r, rule_key)


def _blocked_active_codes_for_rule(rule: dict) -> List[str]:
    """Bloqueos para cola de modo: IN efectivo del panel (override OFF libera), sin forzar lectura física."""
    return [
        code
        for code in rule.get("blocked_if_active", [])
        if _blocked_signal_active(
            code,
            use_hardware_if_no_override=True,
            use_overrides=True,
            physical_inputs=False,
        )
    ]


def _set_pending_manual_enclavamiento(rule_key: str, blocked_inputs: Optional[List[str]] = None) -> None:
    global pending_manual_enclavamiento_mode
    pending_manual_enclavamiento_mode = rule_key
    add_event(
        "INFO",
        f"Modo {rule_key} en cola (esperando liberar bloqueos)",
        1,
    )
    _notify_tablets_mode_queued(rule_key, blocked_inputs)


def _clear_pending_manual_enclavamiento() -> None:
    global pending_manual_enclavamiento_mode
    had_pending = pending_manual_enclavamiento_mode is not None
    pending_manual_enclavamiento_mode = None
    if had_pending:
        _notify_tablets_mode_queued(None)


def _notify_tablets_mode_queued(
    pending_mode: Optional[str],
    blocked_inputs: Optional[List[str]] = None,
) -> None:
    try:
        from app.services import tablet_call_hub

        tablet_call_hub.notify_mode_queued(pending_mode, blocked_inputs)
    except Exception:  # noqa: BLE001
        pass


def _try_execute_pending_manual_enclavamiento(
    *, apply_outputs_to_hardware: bool = True
) -> Optional[dict]:
    """Reintenta el modo en cola cuando ya no hay entradas de bloqueo activas."""
    global pending_manual_enclavamiento_mode
    rk = pending_manual_enclavamiento_mode
    if not rk:
        return None
    rule = rules_config.get(rk)
    if not rule or not rule.get("enabled", True):
        _clear_pending_manual_enclavamiento()
        return None
    if not _rule_eligible_for_manual_queue(rk, rule):
        _clear_pending_manual_enclavamiento()
        return None
    if _blocked_active_codes_for_rule(rule):
        return None
    result = _execute_rule_forced(rk, apply_outputs_to_hardware=apply_outputs_to_hardware)
    if result.get("executed"):
        add_event("OK", f"Modo en cola ejecutado: {rk}", 1)
        return result
    if not result.get("queued"):
        _clear_pending_manual_enclavamiento()
    return result if result.get("executed") else None


def _rule_is_emergency_operational(rule_key: str) -> bool:
    return rule_key in EMERGENCY_MODE_RULE_KEYS


def _is_radares_esclusa_rule(rule_key: str) -> bool:
    return rule_key.startswith("radares_") and rule_key.endswith("_esclusa")


def _is_radares_automatico_rule(rule_key: str) -> bool:
    return rule_key.startswith("radares_") and not rule_key.endswith("_esclusa")


def _rule_participates_in_auto_cycle(rule_key: str, rule: Optional[dict] = None) -> bool:
    """
    Radares «normales» y «_esclusa» comparten el mismo IN físico: solo evalúa la variante
    coherente con `current_mode` (automático vs esclusa).
    """
    if _is_radares_esclusa_rule(rule_key):
        return current_mode == "horario_esclusa"
    if _is_radares_automatico_rule(rule_key):
        return current_mode != "horario_esclusa"
    return True


def _is_toggle_enclavamiento_rule(rule_key: str, rule: Optional[dict] = None) -> bool:
    """
    Enclavamiento tipo interruptor: ON/OFF al pulsar (lateral o IN), sin mantener apretado.
    Excluye solo horarios (IN1–IN7) e incendio global. El resto de `enclavamiento` en JSON es interruptor.
    Los «timbre» (pulso N s) son `pulso_5_sg`, no entran aquí.
    """
    r = rule if rule is not None else rules_config.get(rule_key) or {}
    if r.get("type") != "enclavamiento":
        return False
    if rule_key.startswith(HORARIO_MODE_KEY_PREFIX):
        return False
    if _rule_is_emergency_operational(rule_key):
        return False
    return True


def _pymodbus_client_kwargs() -> Dict[str, Any]:
    """Timeout y reintentos desde .env (antes panel ignoraba modbus_timeout y usaba 8s + retries por defecto)."""
    return {
        "timeout": float(settings.modbus_timeout),
        "retries": max(0, int(settings.modbus_retries)),
    }

pms.ensure_panel_modules_schema()
pms.seed_default_modules_if_empty()
pms.sync_channel_names_from_catalog(only_if_empty=True)

clients: Dict[int, Optional[Any]] = {}
io_state: Dict[int, dict] = {}
input_overrides: Dict[int, List[Optional[bool]]] = {}
serial_client: Optional[ModbusSerialClient] = None
# RTU: un solo bus serie → un lock global. TCP: un RLock por placa (conexiones IP independientes).
modbus_io_lock = threading.RLock()
_board_modbus_locks: Dict[int, threading.RLock] = {}
_board_modbus_locks_guard = threading.Lock()


def _board_modbus_lock(board_id: int) -> threading.RLock:
    """Candado de I/O Modbus para una placa. En RTU devuelve el lock del bus compartido."""
    if _is_rtu_mode():
        return modbus_io_lock
    with _board_modbus_locks_guard:
        lock = _board_modbus_locks.get(board_id)
        if lock is None:
            lock = threading.RLock()
            _board_modbus_locks[board_id] = lock
        return lock


def _drop_board_modbus_lock(board_id: int) -> None:
    with _board_modbus_locks_guard:
        _board_modbus_locks.pop(board_id, None)


# Tras fallo al abrir el puerto serie (p. ej. COM inexistente en PC remoto), evita spam de pymodbus/logs cada ciclo.
_rtu_connect_skip_until: float = 0.0
_RTU_OPEN_FAIL_BACKOFF_SEC: float = 60.0
# Por placa: tras rechazo TCP (p. ej. WinError 10061 puerto mal), evita spam pymodbus en cada ciclo.
_tcp_connect_skip_until: Dict[int, float] = {}
_TCP_OPEN_FAIL_BACKOFF_SEC: float = 60.0
# Por placa: fallos seguidos de _read_all_io antes de marcar connected=False (histéresis en bus ruidoso).
_read_io_fail_streak: Dict[int, int] = {}


def _reset_read_io_fail_streak(board_id: int) -> None:
    _read_io_fail_streak.pop(board_id, None)


def _connect_backoff_active(board_id: int) -> bool:
    """True si un intento de conexión reciente falló y aún no toca reintentar."""
    if _is_rtu_mode():
        return time.monotonic() < _rtu_connect_skip_until
    skip = _tcp_connect_skip_until.get(board_id)
    return skip is not None and time.monotonic() < skip


def _module_ids() -> List[int]:
    return pms.list_module_ids_ordered()


def _board_cfg(board_id: int) -> dict:
    cfg = pms.get_boards_config_map().get(board_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Módulo {board_id} no existe")
    return cfg


def _board_exists(board_id: int) -> bool:
    return board_id in pms.get_boards_config_map()


def _modbus_mode() -> str:
    mode = (settings.modbus_mode or "tcp").strip().lower()
    return mode if mode in {"tcp", "rtu"} else "tcp"


def _is_rtu_mode() -> bool:
    return _modbus_mode() == "rtu"


def _client_is_open(client: Any) -> bool:
    if client is None:
        return False
    if hasattr(client, "is_socket_open"):
        try:
            return bool(client.is_socket_open())
        except Exception:
            return False
    if hasattr(client, "connected"):
        return bool(getattr(client, "connected"))
    return True


def _sync_runtime_from_db() -> None:
    """Alinea clientes en memoria, tamaños de I/O y overrides con la configuración en SQLite."""
    global clients, io_state, input_overrides
    mids = _module_ids()
    for old in list(clients.keys()):
        if old not in mids:
            with _board_modbus_lock(old):
                c = clients.pop(old, None)
                if c:
                    try:
                        c.close()
                    except Exception:
                        pass
            _drop_board_modbus_lock(old)
    for old in list(io_state.keys()):
        if old not in mids:
            io_state.pop(old, None)
            _read_io_fail_streak.pop(old, None)
    for old in list(input_overrides.keys()):
        if old not in mids:
            input_overrides.pop(old, None)
    for mid in mids:
        if mid not in clients:
            clients[mid] = None
        ins, outs = pms.get_channels_for_module(mid)
        n_in, n_out = len(ins), len(outs)
        prev = io_state.get(mid, {})
        prev_in_raw: List[bool] = list(prev.get("inputs_raw") or [])
        prev_out: List[bool] = list(prev.get("outputs") or [])
        prev_eff: List[bool] = list(prev.get("inputs") or [])
        io_state[mid] = {
            "connected": prev.get("connected", False),
            "inputs_raw": [prev_in_raw[i] if i < len(prev_in_raw) else False for i in range(n_in)],
            "outputs": [prev_out[i] if i < len(prev_out) else False for i in range(n_out)],
            "inputs": [prev_eff[i] if i < len(prev_eff) else False for i in range(n_in)],
            "last_update": prev.get("last_update"),
            "error": prev.get("error"),
            "in_out_associated": prev.get("in_out_associated"),
            "pulse_baseline_set": prev.get("pulse_baseline_set", False),
        }
        o_prev = input_overrides.get(mid, [])
        input_overrides[mid] = [
            (o_prev[i] if i < len(o_prev) and o_prev[i] in (None, True, False) else None) for i in range(n_in)
        ]
mode_latches: Dict[str, bool] = {}
# IN trigger de reglas enclavamiento → clave de modo (p. ej. IN_01_05 → horario_cerrado).
in_trigger_to_mode: Dict[str, str] = {}
current_mode: Optional[str] = None
previous_operational_mode: Optional[str] = None
active_toggle_rules: set[str] = set()
DEFAULT_RULES_CONFIG: Dict[str, dict] = {}
BACKEND_DIR = Path(__file__).resolve().parents[3]
RULES_FILE = BACKEND_DIR / "data" / "panel_rules.json"


def _load_rules_from_disk() -> Dict[str, dict]:
    try:
        if RULES_FILE.exists():
            raw = json.loads(RULES_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception:  # noqa: BLE001
        # Si falla lectura, se continúa sin reglas.
        pass
    return DEFAULT_RULES_CONFIG.copy()


def _save_rules_to_disk(rules: Dict[str, dict]) -> None:
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")


rules_config: Dict[str, dict] = _load_rules_from_disk()
rules_runtime: Dict[str, dict] = {}
pending_manual_enclavamiento_mode: Optional[str] = None
background_auto_rules_last_run_at: Optional[str] = None
background_auto_rules_last_result: Dict[str, Any] = {}
background_auto_rules_last_error: Optional[str] = None


def _sync_mode_latches_from_rules(rules: Dict[str, dict]) -> None:
    """Asegura entradas en mode_latches y el mapa IN trigger → modo enclavamiento."""
    global in_trigger_to_mode
    trigger_map: Dict[str, str] = {}
    for rk, rule in rules.items():
        tc = rule.get("trigger")
        if (
            rule.get("type") == "enclavamiento"
            and isinstance(tc, str)
            and tc.startswith("IN_")
        ):
            trigger_map[tc] = rk
        if isinstance(tc, str) and tc.startswith("IN_"):
            mode_latches.setdefault(tc, False)
        for code in rule.get("blocked_if_active") or []:
            if isinstance(code, str) and code.startswith("IN_"):
                mode_latches.setdefault(code, False)
        for code in rule.get("deactivate_modes") or []:
            if isinstance(code, str) and code.startswith("IN_"):
                mode_latches.setdefault(code, False)
    in_trigger_to_mode = trigger_map


def _sync_rules_runtime(rules: Dict[str, dict]) -> None:
    global rules_runtime
    for k in list(rules_runtime.keys()):
        if k not in rules:
            rules_runtime.pop(k, None)
    for k in rules.keys():
        if k not in rules_runtime:
            rules_runtime[k] = {
                "last_trigger_active": False,
                "last_executed_at": None,
                "pulse_until": None,
                "last_follow_on": False,
            }
        else:
            rules_runtime[k].setdefault("pulse_until", None)
            rules_runtime[k].setdefault("last_follow_on", False)
            rules_runtime[k].setdefault("temp_deact_snapshot", {})


_sync_mode_latches_from_rules(rules_config)
_sync_rules_runtime(rules_config)

PANEL_STATE_OVERRIDES_KEY = "panel_input_overrides"
PANEL_STATE_CURRENT_MODE_KEY = "panel_current_mode"
PANEL_STATE_PREVIOUS_MODE_KEY = "panel_previous_operational_mode"
PANEL_STATE_ACTIVE_TOGGLE_RULES_KEY = "panel_active_toggle_rules"


def _ensure_panel_state_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _save_panel_state_value(key: str, value: str) -> None:
    _ensure_panel_state_table()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO panel_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, datetime.now().isoformat()),
        )
        conn.commit()


def _load_panel_state_value(key: str) -> Optional[str]:
    _ensure_panel_state_table()
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM panel_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None


def _persist_overrides_to_db() -> None:
    data = {str(mid): input_overrides[mid] for mid in _module_ids() if mid in input_overrides}
    _save_panel_state_value(PANEL_STATE_OVERRIDES_KEY, json.dumps(data))


def _persist_current_mode_to_db() -> None:
    _save_panel_state_value(PANEL_STATE_CURRENT_MODE_KEY, json.dumps({"current_mode": current_mode}))


def _persist_previous_operational_mode_to_db() -> None:
    _save_panel_state_value(
        PANEL_STATE_PREVIOUS_MODE_KEY,
        json.dumps({"previous_operational_mode": previous_operational_mode}),
    )


def _persist_active_toggle_rules_to_db() -> None:
    _save_panel_state_value(
        PANEL_STATE_ACTIVE_TOGGLE_RULES_KEY,
        json.dumps({"active_toggle_rules": sorted(active_toggle_rules)}),
    )


def _notify_toggle_rules_changed() -> None:
    _persist_active_toggle_rules_to_db()
    _coce_notify(
        "toggle_rules_changed",
        {"active_toggle_rules": sorted(active_toggle_rules)},
    )
    _publish_panel_status_debounced()


def _stash_operational_mode_before_emergency() -> None:
    """Guarda el horario vigente antes de activar incendio/emergencia (como la tablet)."""
    global previous_operational_mode
    if (
        current_mode
        and current_mode.startswith(HORARIO_MODE_KEY_PREFIX)
        and not _rule_is_emergency_operational(current_mode)
    ):
        previous_operational_mode = current_mode
        _persist_previous_operational_mode_to_db()


def _restore_operational_mode_after_emergency() -> None:
    """Al soltar emergencia/incendio, restaura el horario anterior si su IN sigue activo."""
    global current_mode, previous_operational_mode
    prev = previous_operational_mode
    previous_operational_mode = None
    _persist_previous_operational_mode_to_db()
    restored: Optional[str] = None
    if prev:
        rule = rules_config.get(prev) or {}
        trigger = rule.get("trigger")
        if isinstance(trigger, str) and trigger:
            try:
                still_on = _read_input_effective(
                    trigger,
                    use_hardware_if_no_override=True,
                    use_overrides=True,
                    physical_inputs=bool(settings.panel_rules_triggers_use_physical_inputs),
                )
            except Exception:  # noqa: BLE001
                still_on = False
            if still_on:
                restored = prev
    current_mode = restored
    _persist_current_mode_to_db()
    _coce_notify("mode_changed", {"current_mode": current_mode})
    _zaguan_mode_changed(current_mode)


def _load_persisted_panel_state() -> None:
    global current_mode, previous_operational_mode, active_toggle_rules
    _sync_runtime_from_db()
    raw_overrides = _load_panel_state_value(PANEL_STATE_OVERRIDES_KEY)
    if raw_overrides:
        try:
            data = json.loads(raw_overrides)
            if isinstance(data, dict):
                for board_key, values in data.items():
                    board_id = int(board_key)
                    if board_id in input_overrides and isinstance(values, list):
                        n = len(input_overrides[board_id])
                        merged = [v if v in (None, True, False) else None for v in values[:n]]
                        while len(merged) < n:
                            merged.append(None)
                        input_overrides[board_id] = merged
        except Exception:  # noqa: BLE001
            pass

    raw_mode = _load_panel_state_value(PANEL_STATE_CURRENT_MODE_KEY)
    if raw_mode:
        try:
            mode_obj = json.loads(raw_mode)
            mode_value = mode_obj.get("current_mode")
            if isinstance(mode_value, str) or mode_value is None:
                current_mode = mode_value
        except Exception:  # noqa: BLE001
            pass

    raw_prev = _load_panel_state_value(PANEL_STATE_PREVIOUS_MODE_KEY)
    if raw_prev:
        try:
            prev_obj = json.loads(raw_prev)
            prev_value = prev_obj.get("previous_operational_mode")
            if isinstance(prev_value, str) or prev_value is None:
                previous_operational_mode = prev_value
        except Exception:  # noqa: BLE001
            pass

    raw_toggles = _load_panel_state_value(PANEL_STATE_ACTIVE_TOGGLE_RULES_KEY)
    if raw_toggles:
        try:
            tobj = json.loads(raw_toggles)
            keys = tobj.get("active_toggle_rules")
            if isinstance(keys, list):
                active_toggle_rules = {
                    str(k)
                    for k in keys
                    if isinstance(k, str) and k in rules_config
                    and _is_toggle_enclavamiento_rule(k)
                }
        except Exception:  # noqa: BLE001
            pass


_load_persisted_panel_state()


def add_event(level: str, message: str, board_id: int = 0) -> None:
    """Registra evento en SQLite (actor desde contexto panel/tablet o system)."""
    try:
        ses.record_event(level, message, board_id=board_id)
    except Exception:  # noqa: BLE001
        # No bloquear operación crítica si falla el log
        pass


def get_client(board_id: int) -> Any:
    _board_cfg(board_id)
    client = clients.get(board_id)
    if not _client_is_open(client):
        raise HTTPException(status_code=503, detail=f"Módulo {board_id} no conectado")
    return client


def _probe_register_address(board_id: int) -> int:
    ins, outs = pms.get_channels_for_module(board_id)
    if ins:
        return int(ins[0]["address"])
    if outs:
        return int(outs[0]["address"])
    return REG_INPUT_START


def _connect_board(board_id: int) -> bool:
    global serial_client, _rtu_connect_skip_until, _tcp_connect_skip_until
    cfg = dict(_board_cfg(board_id))
    try:
        if _is_rtu_mode():
            if time.monotonic() < _rtu_connect_skip_until:
                io_state[board_id]["connected"] = False
                io_state[board_id]["error"] = (
                    f"RTU en pausa tras fallo de puerto; reintento en "
                    f"{int(_rtu_connect_skip_until - time.monotonic())}s "
                    f"(o use MODBUS_MODE=tcp en .env)"
                )
                return False
            with modbus_io_lock:
                if serial_client is None:
                    serial_client = ModbusSerialClient(
                        port=settings.modbus_serial_port,
                        baudrate=settings.modbus_serial_baudrate,
                        bytesize=settings.modbus_serial_bytesize,
                        parity=settings.modbus_serial_parity,
                        stopbits=settings.modbus_serial_stopbits,
                        **_pymodbus_client_kwargs(),
                    )
                if not _client_is_open(serial_client):
                    ok = serial_client.connect()
                    if not ok:
                        _rtu_connect_skip_until = time.monotonic() + _RTU_OPEN_FAIL_BACKOFF_SEC
                        io_state[board_id]["connected"] = False
                        io_state[board_id]["error"] = (
                            f"No se pudo abrir puerto serial {settings.modbus_serial_port}"
                        )
                        add_event(
                            "ERR",
                            f"RTU no conectado en {settings.modbus_serial_port}",
                            board_id,
                        )
                        return False

                # Mismo criterio que TCP: no barrer 1/2/3/255 ni persistir un slave distinto al
                # configurado (en RS-485 suele haber varios nodos; el primero que responda podía
                # machacar en BD el slave de otra placa o un valor por defecto).
                candidate_slave = int(cfg["slave_id"])
                last_probe_error: Optional[str] = None
                try:
                    probe_addr = _probe_register_address(board_id)
                    probe = serial_client.read_holding_registers(
                        address=probe_addr,
                        count=1,
                        device_id=candidate_slave,
                    )
                    if probe.isError():
                        raise RuntimeError(f"Probe Modbus error: {probe}")
                    clients[board_id] = serial_client
                    io_state[board_id]["connected"] = True
                    io_state[board_id]["error"] = None
                    add_event(
                        "OK",
                        f"RTU conectado en {settings.modbus_serial_port} (slave_id={candidate_slave})",
                        board_id,
                    )
                    _rtu_connect_skip_until = 0.0
                except Exception as probe_err:  # noqa: BLE001
                    last_probe_error = str(probe_err)
                    io_state[board_id]["connected"] = False
                    io_state[board_id]["error"] = (
                        f"RTU no operativo (slave_id={candidate_slave}): {last_probe_error}"
                    )
                    add_event(
                        "ERR",
                        f"RTU no operativo (slave_id={candidate_slave}): {last_probe_error}",
                        board_id,
                    )
                    return False
        else:
            tcp_skip = _tcp_connect_skip_until.get(board_id)
            if tcp_skip is not None and time.monotonic() < tcp_skip:
                io_state[board_id]["connected"] = False
                io_state[board_id]["error"] = (
                    f"TCP {cfg['host']}:{cfg['port']} en pausa tras fallo; "
                    f"reintento en {max(0, int(tcp_skip - time.monotonic()))}s "
                    f"(comprueba puerto Modbus, suele ser 502)"
                )
                return False
            # Un solo hilo a la vez por socket de esta placa: evita mezcla de transaction_id
            # en la misma IP; otras placas usan su propio lock (_board_modbus_lock).
            with _board_modbus_lock(board_id):
                if clients[board_id]:
                    try:
                        clients[board_id].close()
                    except Exception:
                        pass
                # TCP: un destino IP = un dispositivo; no probar otros slave_id (1/255) porque
                # podían responder y sobrescribir en BD el valor que el usuario acababa de guardar.
                candidate_slave = int(cfg["slave_id"])

                client = ModbusTcpClient(host=cfg["host"], port=cfg["port"], **_pymodbus_client_kwargs())
                ok = client.connect()
                if not ok:
                    last_probe_error = "No se pudo establecer conexión TCP"
                    try:
                        client.close()
                    except Exception:
                        pass
                    _tcp_connect_skip_until[board_id] = time.monotonic() + _TCP_OPEN_FAIL_BACKOFF_SEC
                    io_state[board_id]["connected"] = False
                    io_state[board_id]["error"] = last_probe_error
                    add_event(
                        "ERR",
                        f"TCP {cfg['host']}:{cfg['port']}: {last_probe_error}",
                        board_id,
                    )
                    return False

                clients[board_id] = client
                io_state[board_id]["connected"] = True
                io_state[board_id]["error"] = None
                add_event(
                    "OK",
                    f"TCP conectado a {cfg['host']}:{cfg['port']} (slave_id={candidate_slave})",
                    board_id,
                )

                try:
                    probe_addr = _probe_register_address(board_id)
                    probe = client.read_holding_registers(
                        address=probe_addr, count=1, device_id=candidate_slave
                    )
                    if probe.isError():
                        raise RuntimeError(f"Probe Modbus error: {probe}")
                except Exception as probe_err:  # noqa: BLE001
                    last_probe_error = str(probe_err)
                    io_state[board_id]["connected"] = False
                    io_state[board_id]["error"] = f"TCP ok pero Modbus no operativo: {probe_err}"
                    try:
                        client.close()
                    except Exception:
                        pass
                    clients[board_id] = None
                    add_event(
                        "ERR",
                        f"TCP Modbus no operativo (slave_id={candidate_slave}): {last_probe_error}",
                        board_id,
                    )
                    _tcp_connect_skip_until[board_id] = time.monotonic() + _TCP_OPEN_FAIL_BACKOFF_SEC
                    return False

                _tcp_connect_skip_until.pop(board_id, None)
        # ETD8A12: desacoplar IN↔OUT de fábrica (ver `etd_disable_in_out_association_on_connect` en .env).
        if settings.etd_disable_in_out_association_on_connect:
            rel = cfg.get("relation_register")
            if rel is None:
                add_event(
                    "WARN",
                    "Desacople IN/OUT omitido: relation_register no definido en BD para este módulo",
                    board_id,
                )
            else:
                try:
                    with _board_modbus_lock(board_id):
                        c = clients.get(board_id)
                        if c is None:
                            add_event(
                                "WARN",
                                "Desacople IN/OUT omitido: cliente Modbus no disponible",
                                board_id,
                            )
                        else:
                            sid = int(cfg["slave_id"])
                            addr = int(rel)
                            result = c.write_register(
                                address=addr,
                                value=0x0000,
                                device_id=sid,
                            )
                            if hasattr(result, "isError") and result.isError():
                                add_event(
                                    "ERR",
                                    f"Desacople IN/OUT Modbus error en 0x{addr:04X} slave={sid}: {result}",
                                    board_id,
                                )
                            else:
                                add_event(
                                    "OK",
                                    f"Desacople IN/OUT aplicado: holding 0x{addr:04X} ({addr})=0, slave_id={sid}",
                                    board_id,
                                )
                except Exception as ex:  # noqa: BLE001
                    add_event("ERR", f"Desacople IN/OUT excepción: {ex}", board_id)
        return True
    except Exception as e:  # noqa: BLE001
        io_state[board_id]["connected"] = False
        io_state[board_id]["error"] = str(e)
        add_event("ERR", f"Excepción al conectar: {e}", board_id)
        return False


def _read_holding_block_if_contiguous(client: Any, slave: int, channels: List[dict]) -> Optional[List[bool]]:
    """
    Una sola read_holding_registers si los addresses de `channels` (en orden actual)
    son consecutivos. Caso típico ETD8A12: 12 OUT en 0x0000.. y 12 IN en 0x0080..
    Devuelve lista de bool o None si no aplica / error Modbus.
    """
    if not channels:
        return []
    addrs = [int(ch["address"]) for ch in channels]
    base = addrs[0]
    for i, a in enumerate(addrs):
        if a != base + i:
            return None
    n = len(addrs)
    res = client.read_holding_registers(address=base, count=n, device_id=slave)
    if res.isError() or not getattr(res, "registers", None) or len(res.registers) < n:
        return None
    return [bool(res.registers[i]) for i in range(n)]


def _track_input_pulse_rising_edges(board_id: int, prev_inputs_raw: tuple[bool, ...]) -> None:
    """Cuenta flancos OFF→ON en inputs_raw (pulsaciones físicas, sin override)."""
    ins, _ = pms.get_channels_for_module(board_id)
    st = io_state.get(board_id)
    if not st:
        return
    if not st.get("pulse_baseline_set"):
        st["pulse_baseline_set"] = True
        return
    current_raw = list(st.get("inputs_raw") or [])
    for i, ch in enumerate(ins):
        if i >= len(prev_inputs_raw) or i >= len(current_raw):
            continue
        if not prev_inputs_raw[i] and current_raw[i]:
            pms.increment_channel_pulse_count(int(ch["id"]))


def _read_all_io(board_id: int, retried: bool = False, *, _modbus_lock_held: bool = False) -> None:
    """
    Lee OUT/IN (y opcionalmente relation_register) vía Modbus.
    Si `_modbus_lock_held=True`, el caller ya tiene `_board_modbus_lock(board_id)` para esta placa
    (evita transaction_id mezclados en el mismo socket TCP).
    """
    client = clients.get(board_id)
    if not _client_is_open(client):
        if board_id in io_state:
            io_state[board_id]["connected"] = False
        _reset_read_io_fail_streak(board_id)
        return

    cfg = _board_cfg(board_id)
    slave = cfg["slave_id"]
    ins, outs = pms.get_channels_for_module(board_id)
    io_before = _io_tuple(board_id)

    def _run_bus_reads() -> None:
        out_batch = _read_holding_block_if_contiguous(client, slave, outs)
        if out_batch is not None and len(out_batch) == len(outs):
            for i, v in enumerate(out_batch):
                io_state[board_id]["outputs"][i] = v
        else:
            for i, ch in enumerate(outs):
                res = client.read_holding_registers(address=int(ch["address"]), count=1, device_id=slave)
                if not res.isError() and res.registers:
                    io_state[board_id]["outputs"][i] = bool(res.registers[0])

        in_batch = _read_holding_block_if_contiguous(client, slave, ins)
        if in_batch is not None and len(in_batch) == len(ins):
            for i, v in enumerate(in_batch):
                io_state[board_id]["inputs_raw"][i] = v
        else:
            for i, ch in enumerate(ins):
                res = client.read_holding_registers(address=int(ch["address"]), count=1, device_id=slave)
                if not res.isError() and res.registers:
                    io_state[board_id]["inputs_raw"][i] = bool(res.registers[0])

        if settings.panel_poll_in_out_relation_register:
            rel_reg = cfg.get("relation_register")
            if rel_reg is not None:
                res_rel = client.read_holding_registers(
                    address=int(rel_reg), count=1, device_id=slave
                )
                if not res_rel.isError() and getattr(res_rel, "registers", None):
                    io_state[board_id]["in_out_associated"] = res_rel.registers[0] != 0

    try:
        if _modbus_lock_held:
            _run_bus_reads()
        else:
            with _board_modbus_lock(board_id):
                _run_bus_reads()

        effective_inputs: List[bool] = []
        for idx in range(len(ins)):
            forced = input_overrides[board_id][idx]
            raw = io_state[board_id]["inputs_raw"][idx]
            effective_inputs.append(raw if forced is None else forced)
        io_state[board_id]["inputs"] = effective_inputs

        _track_input_pulse_rising_edges(board_id, io_before[0])

        io_state[board_id]["connected"] = True
        io_state[board_id]["last_update"] = datetime.now().isoformat()
        io_state[board_id]["error"] = None
        _read_io_fail_streak[board_id] = 0
        if _io_tuple(board_id) != io_before:
            _publish_panel_status_debounced()
    except Exception as e:  # noqa: BLE001
        # Reintento único tras reconexión cuando el equipo resetea socket (WinError 10054).
        if not retried and not _connect_backoff_active(board_id):
            _connect_board(board_id)
            if io_state[board_id]["connected"]:
                return _read_all_io(board_id, retried=True)
        still_open = _client_is_open(clients.get(board_id))
        was_connected = bool(io_state.get(board_id, {}).get("connected"))
        streak = _read_io_fail_streak.get(board_id, 0) + 1
        _read_io_fail_streak[board_id] = streak
        nmax = max(1, min(20, int(settings.panel_modbus_read_failures_before_disconnect)))
        soft_ok = still_open and was_connected and streak < nmax
        if soft_ok:
            io_state[board_id]["connected"] = True
            io_state[board_id]["error"] = (
                f"Lectura Modbus inestable ({streak}/{nmax} fallos seguidos; se mantiene sesión): {e}"
            )
        else:
            io_state[board_id]["connected"] = False
            io_state[board_id]["error"] = str(e)
            _reset_read_io_fail_streak(board_id)
            if not soft_ok and was_connected:
                add_event("WARN", f"Lectura Modbus: placa {board_id} marcada desconectada tras {streak} fallo(s): {e}", board_id)


def _write_output(board_id: int, channel: int, state: bool) -> None:
    client = get_client(board_id)
    cfg = _board_cfg(board_id)
    _, outs = pms.get_channels_for_module(board_id)
    if not 1 <= channel <= len(outs):
        raise HTTPException(status_code=400, detail=f"Canal OUT {channel} inválido para módulo {board_id}")
    ch = outs[channel - 1]
    register = int(ch["address"])
    open_v = int(ch["open_cmd"]) if ch["open_cmd"] is not None else CMD_OPEN
    close_v = int(ch["close_cmd"]) if ch["close_cmd"] is not None else CMD_CLOSE
    value = open_v if state else close_v
    with _board_modbus_lock(board_id):
        result = client.write_register(address=register, value=value, device_id=cfg["slave_id"])
    if result.isError():
        raise HTTPException(status_code=502, detail=f"Error Modbus escribiendo OUT{channel} en módulo {board_id}: {result}")
    io_state[board_id]["outputs"][channel - 1] = state


def _write_output_if_connected(
    board_id: int,
    channel: int,
    state: bool,
    *,
    out_code: str,
    origin: str,
) -> bool:
    """
    Igual que `_write_output` pero si el módulo no tiene sesión Modbus activa no escribe
    (reglas/modos con varias placas: se omiten salidas de las desconectadas).
    """
    if not io_state.get(board_id, {}).get("connected"):
        add_event(
            "WARN",
            f"{origin}: omitida salida {out_code} (módulo {board_id} sin Modbus conectado)",
            board_id,
        )
        return False
    _write_output(board_id, channel, state)
    return True


def _apply_output_for_rule(
    board_id: int,
    channel: int,
    state: bool,
    *,
    out_code: str,
    origin: str,
    apply_outputs_to_hardware: bool,
) -> bool:
    """
    Aplica salida de regla/modo: hardware si la placa está conectada; si no, solo snapshot RAM
    (permite cambiar de modo con una o varias placas offline).
    Devuelve True si se escribió en hardware.
    """
    if apply_outputs_to_hardware:
        if io_state.get(board_id, {}).get("connected"):
            return _write_output_if_connected(
                board_id, channel, state, out_code=out_code, origin=origin
            )
        _, outs = pms.get_channels_for_module(board_id)
        if 1 <= channel <= len(outs):
            io_state[board_id]["outputs"][channel - 1] = state
        return False
    _, outs = pms.get_channels_for_module(board_id)
    if 1 <= channel <= len(outs):
        io_state[board_id]["outputs"][channel - 1] = state
    return False


def _read_input_for_blocker(
    code: str,
    *,
    use_hardware_if_no_override: bool = True,
    use_overrides: bool = True,
    physical_inputs: bool = False,
) -> bool:
    """IN para bloqueos: sin intentar reconectar placas desconectadas (evita 503 en cambio de modo)."""
    board_id, _ = _parse_in_code(code)
    connected = bool(io_state.get(board_id, {}).get("connected"))
    return _read_input_effective(
        code,
        use_hardware_if_no_override=use_hardware_if_no_override and connected,
        use_overrides=use_overrides,
        physical_inputs=physical_inputs if connected else False,
    )


def _parse_in_code(code: str) -> tuple[int, int]:
    parsed = pms.parse_smcse_code(code)
    if parsed:
        kind, module_id, slot_index = parsed
        if kind != "input":
            raise HTTPException(status_code=400, detail=f"{code} no es una entrada (DI)")
        return module_id, slot_index
    parts = code.strip().upper().split("_")
    if len(parts) == 3 and parts[0] == "IN":
        return int(parts[1]), int(parts[2])
    if len(parts) == 4 and parts[0] == "DI":
        return int(parts[2]), int(parts[3])
    raise HTTPException(status_code=400, detail=f"Código de entrada inválido: {code}")


def _parse_out_code(code: str) -> tuple[int, int]:
    parsed = pms.parse_smcse_code(code)
    if parsed:
        kind, module_id, slot_index = parsed
        if kind != "output":
            raise HTTPException(status_code=400, detail=f"{code} no es una salida (DO)")
        return module_id, slot_index
    parts = code.strip().upper().split("_")
    if len(parts) == 3 and parts[0] == "OUT":
        return int(parts[1]), int(parts[2])
    if len(parts) == 4 and parts[0] == "DO":
        return int(parts[2]), int(parts[3])
    raise HTTPException(status_code=400, detail=f"Código de salida inválido: {code}")


def _read_input_effective(
    code: str,
    use_hardware_if_no_override: bool = True,
    use_overrides: bool = True,
    *,
    physical_inputs: bool = False,
) -> bool:
    board_id, channel = _parse_in_code(code)
    if not _board_exists(board_id):
        raise HTTPException(status_code=400, detail=f"Módulo inválido en {code}")
    ins, _ = pms.get_channels_for_module(board_id)
    if not 1 <= channel <= len(ins):
        raise HTTPException(status_code=400, detail=f"Canal inválido en {code}")
    if use_overrides and not physical_inputs:
        forced = input_overrides[board_id][channel - 1]
        if forced is not None:
            return forced
    idx = channel - 1
    if not use_hardware_if_no_override:
        raw_list = list(io_state[board_id].get("inputs_raw") or [])
        raw = bool(raw_list[idx]) if idx < len(raw_list) else False
        if physical_inputs:
            forced = input_overrides[board_id][idx]
            if use_overrides and forced is True:
                return True
            return raw
        return io_state[board_id]["inputs"][idx]
    if not io_state[board_id]["connected"]:
        _connect_board(board_id)
    if not io_state[board_id]["connected"]:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar placa {board_id} para leer {code}")
    _read_all_io(board_id)
    raw_list = list(io_state[board_id].get("inputs_raw") or [])
    raw = bool(raw_list[idx]) if idx < len(raw_list) else False
    if physical_inputs:
        # Lectura física manda: override OFF no enmascara ON del bus. Override ON (prueba) sigue activando.
        forced = input_overrides[board_id][idx]
        if use_overrides and forced is True:
            return True
        return raw
    return io_state[board_id]["inputs"][idx]


def _horario_blocker_suppressed_by_operative_mode(mode_key: str) -> bool:
    """
    Con un horario operativo distinto, no bloquear por cables «apagados» al activar ese modo
    (p. ej. en Esclusa ignorar IN1 Automático aunque el bus siga alto).
    En Automático sí cuentan los IN de otros horarios (p. ej. Esclusa) para bloquear radares.
    """
    if not current_mode or not mode_key:
        return False
    cur_rule = rules_config.get(current_mode) or {}
    deact = cur_rule.get("deactivate_modes") or []
    blocker_rule = rules_config.get(mode_key) or {}
    blocker_trigger = blocker_rule.get("trigger")
    if not isinstance(blocker_trigger, str) or blocker_trigger not in deact:
        return False
    if current_mode == "horario_automatico":
        return False
    return True


def _blocked_signal_active(
    code: str,
    *,
    use_hardware_if_no_override: bool = True,
    use_overrides: bool = True,
    physical_inputs: bool = False,
) -> bool:
    """True si la condición de bloqueo está activa. IN: efectivo panel (override manda); OUT: salidas."""
    code = (code or "").strip()
    if not code:
        return False
    head = code.split("_")[0].upper()
    if head in ("OUT", "DO"):
        board_id, channel = _parse_out_code(code)
        if not _board_exists(board_id):
            return False
        if use_hardware_if_no_override and io_state.get(board_id, {}).get("connected"):
            try:
                _read_all_io(board_id)
            except Exception:
                pass
        outs = list(io_state.get(board_id, {}).get("outputs") or [])
        if not 1 <= channel <= len(outs):
            return False
        return bool(outs[channel - 1])
    mode_key = in_trigger_to_mode.get(code)
    if mode_key is not None and mode_key.startswith(HORARIO_MODE_KEY_PREFIX):
        if current_mode == mode_key:
            return True
        if _horario_blocker_suppressed_by_operative_mode(mode_key):
            return False
        return _read_input_for_blocker(
            code,
            use_hardware_if_no_override=use_hardware_if_no_override,
            use_overrides=use_overrides,
            physical_inputs=physical_inputs,
        )
    return _read_input_for_blocker(
        code,
        use_hardware_if_no_override=use_hardware_if_no_override,
        use_overrides=use_overrides,
        physical_inputs=physical_inputs,
    )


def _default_rule_runtime(rule_key: str) -> dict:
    if rule_key not in rules_runtime:
        rules_runtime[rule_key] = {
            "last_trigger_active": False,
            "last_executed_at": None,
            "pulse_until": None,
            "last_follow_on": False,
            "temp_deact_snapshot": {},
            "temp_deact_restore_at": None,
        }
    rules_runtime[rule_key].setdefault("pulse_until", None)
    rules_runtime[rule_key].setdefault("last_follow_on", False)
    rules_runtime[rule_key].setdefault("temp_deact_snapshot", {})
    rules_runtime[rule_key].setdefault("temp_deact_restore_at", None)
    rules_runtime[rule_key].setdefault("pulse_trigger_panel_override", False)
    return rules_runtime[rule_key]


def _clear_pulse_trigger_override_after_panel_pulse(rule_key: str, rule: dict, runtime: dict) -> None:
    """Tras un pulso temporizado disparado por override, libera el IN (null) para ver el estado real."""
    if not runtime.pop("pulse_trigger_panel_override", False):
        return
    trigger_code = rule.get("trigger")
    if not isinstance(trigger_code, str) or not trigger_code:
        return
    board_id, channel = _parse_in_code(trigger_code)
    input_overrides[board_id][channel - 1] = None
    _persist_overrides_to_db()
    add_event("INFO", f"Pulso finalizado: override liberado en {trigger_code} ({rule_key})", 1)


def _finish_timed_pulse(
    rule: dict,
    rule_key: str,
    runtime: dict,
    *,
    apply_outputs_to_hardware: bool,
    origin: str,
) -> None:
    """Apaga salidas del pulso, restaura desactivación temporal y limpia override del trigger si tocaba."""
    _restore_temp_deactivate_outputs(
        rule, rule_key, apply_outputs_to_hardware, origin=origin
    )
    _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, False, rule_key=rule_key)
    runtime["pulse_until"] = None
    _clear_pulse_trigger_override_after_panel_pulse(rule_key, rule, runtime)


def _rule_deactivate_outputs_temporary(rule: dict) -> bool:
    """Si True, al soltar la regla se restauran solo los OUT que estaban ON antes de forzarlos a OFF."""
    return bool(rule.get("deactivate_outputs_temporary"))


def _cancel_pending_temp_deactivate_restore(rule_key: str) -> None:
    runtime = rules_runtime.get(rule_key)
    if runtime is not None:
        runtime["temp_deact_restore_at"] = None


def _read_output_cached(board_id: int, channel: int) -> bool:
    outs = list(io_state.get(board_id, {}).get("outputs") or [])
    if 1 <= channel <= len(outs):
        return bool(outs[channel - 1])
    return False


def _snapshot_temp_deactivate_outputs(rule: dict, rule_key: str) -> None:
    """Guarda en runtime qué OUT de deactivate_outputs estaban ON antes de apagarlos."""
    if not _rule_deactivate_outputs_temporary(rule):
        return
    _cancel_pending_temp_deactivate_restore(rule_key)
    runtime = _default_rule_runtime(rule_key)
    snap: Dict[str, bool] = {}
    for do_code in rule.get("deactivate_outputs") or []:
        try:
            board_id, channel = _parse_out_code(do_code)
        except HTTPException:
            continue
        if _read_output_cached(board_id, channel):
            snap[do_code] = True
    runtime["temp_deact_snapshot"] = snap


def _clear_temp_deactivate_snapshot(rule_key: str) -> None:
    if rule_key in rules_runtime:
        rules_runtime[rule_key]["temp_deact_snapshot"] = {}


def _restore_temp_deactivate_outputs(
    rule: dict,
    rule_key: str,
    apply_outputs_to_hardware: bool,
    *,
    origin: str,
    force_immediate: bool = False,
) -> List[str]:
    """Vuelve a ON los OUT que estaban ON en el snapshot (desactivación temporal)."""
    if not _rule_deactivate_outputs_temporary(rule):
        return []
    runtime = _default_rule_runtime(rule_key)
    snap: Dict[str, bool] = dict(runtime.get("temp_deact_snapshot") or {})
    if not any(snap.values()):
        _cancel_pending_temp_deactivate_restore(rule_key)
        return []
    if not force_immediate:
        try:
            delay = int(settings.panel_temp_deactivate_restore_delay_seconds)
        except (TypeError, ValueError):
            delay = 0
        delay = max(0, min(120, delay))
        if delay > 0:
            runtime["temp_deact_restore_at"] = (
                datetime.now() + timedelta(seconds=delay)
            ).isoformat()
            return []
    restored: List[str] = []
    for do_code, was_on in snap.items():
        if not was_on:
            continue
        board_id, channel = _parse_out_code(do_code)
        _apply_output_for_rule(
            board_id,
            channel,
            True,
            out_code=do_code,
            origin=origin,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        )
        restored.append(do_code)
    _clear_temp_deactivate_snapshot(rule_key)
    _cancel_pending_temp_deactivate_restore(rule_key)
    if restored:
        add_event(
            "INFO",
            f"Restauradas salidas (estaban ON antes de la regla): {', '.join(restored)}",
            1,
        )
        # Escritura Modbus actualiza io_state sin pasar por _read_all_io; el siguiente
        # poll no ve delta y el dashboard no recibe panel_status hasta refrescar.
        _publish_panel_status_debounced(force=True)
    return restored


def _process_pending_temp_deactivate_restores(
    apply_outputs_to_hardware: bool = True,
) -> int:
    """Ejecuta restauraciones diferidas cuyo plazo ya venció."""
    now = datetime.now()
    done = 0
    for rule_key, runtime in list(rules_runtime.items()):
        at_str = runtime.get("temp_deact_restore_at")
        if not at_str:
            continue
        at_dt = _parse_iso_datetime(at_str)
        if at_dt is None or now < at_dt:
            continue
        rule = rules_config.get(rule_key)
        if not rule:
            runtime["temp_deact_restore_at"] = None
            continue
        _restore_temp_deactivate_outputs(
            rule,
            rule_key,
            apply_outputs_to_hardware,
            origin=f"restore_delayed:{rule_key}",
            force_immediate=True,
        )
        done += 1
    return done


def _pulse_seconds(rule: dict) -> int:
    """0 = modo detección (sigue nivel del trigger). N>0 = duración del pulso en segundos (máx. 300).
    Sin clave o null = PULSE_5_SG_DEFAULT_SECONDS (0 = detección)."""
    if "pulse_seconds" not in rule:
        return PULSE_5_SG_DEFAULT_SECONDS
    raw = rule.get("pulse_seconds")
    if raw is None:
        return PULSE_5_SG_DEFAULT_SECONDS
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return PULSE_5_SG_DEFAULT_SECONDS
    if n <= 0:
        return 0
    return min(n, 300)


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _apply_deactivate_outputs(
    rule: dict,
    apply_outputs_to_hardware: bool,
    *,
    rule_key: str = "",
    origin: str = "",
) -> None:
    """Apaga deactivate_outputs; si `deactivate_outputs_temporary`, guarda snapshot previo."""
    tag = origin or (f"rule:{rule_key}" if rule_key else "rule")
    if rule_key and _rule_deactivate_outputs_temporary(rule):
        _snapshot_temp_deactivate_outputs(rule, rule_key)
    for do_code in rule.get("deactivate_outputs", []):
        board_id, channel = _parse_out_code(do_code)
        _apply_output_for_rule(
            board_id,
            channel,
            False,
            out_code=do_code,
            origin=tag,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        )


def _pulse_apply_deactivate_outputs(
    rule: dict, apply_outputs_to_hardware: bool, *, rule_key: str = ""
) -> None:
    tag = f"pulso_5_sg:{rule_key}" if rule_key else "pulso_5_sg"
    _apply_deactivate_outputs(rule, apply_outputs_to_hardware, rule_key=rule_key, origin=tag)


def _pulse_apply_activate_outputs(
    rule: dict, apply_outputs_to_hardware: bool, state: bool, *, rule_key: str = ""
) -> None:
    tag = f"pulso_5_sg:{rule_key}" if rule_key else "pulso_5_sg"
    for do_code in rule.get("activate_outputs", []):
        board_id, channel = _parse_out_code(do_code)
        _apply_output_for_rule(
            board_id,
            channel,
            state,
            out_code=do_code,
            origin=tag,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        )


def _evaluate_pulse_5_sg_rule(
    rule_key: str,
    manual: bool = False,
    use_hardware_if_no_override: bool = True,
    use_overrides: bool = True,
    apply_outputs_to_hardware: bool = True,
    *,
    physical_inputs: bool = False,
) -> dict:
    """`pulso_5_sg`: si `pulse_seconds` es 0, seguimiento por nivel del trigger; si N>0, pulso temporizado de N s.
    No modifica `current_mode`."""
    rule = rules_config.get(rule_key)
    if not rule:
        return {"executed": False, "reason": f"Regla no encontrada: {rule_key}"}
    runtime = _default_rule_runtime(rule_key)
    secs = _pulse_seconds(rule)

    if not rule.get("enabled", True):
        if runtime.get("last_follow_on"):
            _restore_temp_deactivate_outputs(
                rule, rule_key, apply_outputs_to_hardware, origin=f"pulso_off:{rule_key}"
            )
            _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, False, rule_key=rule_key)
            runtime["last_follow_on"] = False
        if runtime.get("pulse_until"):
            _finish_timed_pulse(
                rule,
                rule_key,
                runtime,
                apply_outputs_to_hardware=apply_outputs_to_hardware,
                origin=f"pulso_fin:{rule_key}",
            )
            add_event("INFO", f"Pulso finalizado: {rule_key}", 1)
        return {"executed": False, "reason": "Regla deshabilitada"}

    if secs > 0:
        now = datetime.now()
        end_dt = _parse_iso_datetime(runtime.get("pulse_until"))
        if end_dt is not None and now >= end_dt:
            _finish_timed_pulse(
                rule,
                rule_key,
                runtime,
                apply_outputs_to_hardware=apply_outputs_to_hardware,
                origin=f"pulso_fin:{rule_key}",
            )
            add_event("INFO", f"Pulso finalizado: {rule_key}", 1)

        trigger_code = rule.get("trigger", "IN_01_01")
        trigger_active = _read_input_effective(
            trigger_code,
            use_hardware_if_no_override=use_hardware_if_no_override,
            use_overrides=use_overrides,
            physical_inputs=physical_inputs,
        )
        blocked_codes = rule.get("blocked_if_active", [])
        blocked_active_codes = [
            code
            for code in blocked_codes
            if _blocked_signal_active(
                code,
                use_hardware_if_no_override=use_hardware_if_no_override,
                use_overrides=use_overrides,
                physical_inputs=physical_inputs,
            )
        ]

        if runtime.get("pulse_until"):
            runtime["last_trigger_active"] = trigger_active
            return {
                "executed": False,
                "reason": "Pulso en curso",
                "trigger_input_active": trigger_active,
                "pulse_until": runtime.get("pulse_until"),
                "pulse_seconds": secs,
                "follow_mode": False,
            }

        if not manual:
            rising_edge = trigger_active and not runtime["last_trigger_active"]
            runtime["last_trigger_active"] = trigger_active
            if not rising_edge:
                return {
                    "executed": False,
                    "reason": "Sin flanco de subida en trigger",
                    "trigger_input_active": trigger_active,
                    "pulse_seconds": secs,
                    "follow_mode": False,
                }
        elif not trigger_active:
            return {
                "executed": False,
                "reason": f"No se ejecuta: {trigger_code} no está activa",
                "trigger_input_active": False,
                "pulse_seconds": secs,
                "follow_mode": False,
            }

        if blocked_active_codes:
            _clear_trigger_input_override(trigger_code)
            add_event("WARN", f"{rule_key} bloqueado por {', '.join(blocked_active_codes)}", 1)
            return {
                "executed": False,
                "reason": f"Bloqueado por entradas activas: {', '.join(blocked_active_codes)}",
                "trigger_input_active": trigger_active,
                "blocked_inputs": blocked_active_codes,
                "pulse_seconds": secs,
                "follow_mode": False,
            }

        _pulse_apply_deactivate_outputs(rule, apply_outputs_to_hardware, rule_key=rule_key)
        _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, True, rule_key=rule_key)
        until = now + timedelta(seconds=secs)
        runtime["pulse_until"] = until.isoformat()
        runtime["pulse_trigger_panel_override"] = _trigger_activated_by_panel_override(
            trigger_code, manual=manual
        )
        runtime["last_executed_at"] = now.isoformat()
        add_event("OK", f"Pulso {secs}s iniciado: {rule_key}", 1)
        return {
            "executed": True,
            "mode": current_mode,
            "trigger_input_active": trigger_active,
            "blocked_inputs": blocked_active_codes,
            "outputs_activated": rule.get("activate_outputs", []),
            "outputs_deactivated": rule.get("deactivate_outputs", []),
            "pulse_seconds": secs,
            "pulse_until": runtime["pulse_until"],
            "follow_mode": False,
            "timestamp": runtime["last_executed_at"],
        }

    # --- Modo detección (pulse_seconds == 0): sigue nivel del trigger ---
    if runtime.get("pulse_until"):
        _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, False, rule_key=rule_key)
        runtime["pulse_until"] = None

    trigger_code = rule.get("trigger", "IN_01_01")
    trigger_active = _read_input_effective(
        trigger_code,
        use_hardware_if_no_override=use_hardware_if_no_override,
        use_overrides=use_overrides,
        physical_inputs=physical_inputs,
    )
    blocked_codes = rule.get("blocked_if_active", [])
    blocked_active_codes = [
        code
        for code in blocked_codes
        if _blocked_signal_active(
            code,
            use_hardware_if_no_override=use_hardware_if_no_override,
            use_overrides=use_overrides,
            physical_inputs=physical_inputs,
        )
    ]
    desired = bool(trigger_active) and not blocked_active_codes
    last = bool(runtime.get("last_follow_on"))
    rising = bool(trigger_active) and not bool(runtime.get("last_trigger_active"))

    if rising and blocked_active_codes:
        _clear_trigger_input_override(trigger_code)
        runtime["last_trigger_active"] = trigger_active
        add_event("WARN", f"{rule_key} bloqueado por {', '.join(blocked_active_codes)}", 1)
        return {
            "executed": False,
            "reason": f"Bloqueado por entradas activas: {', '.join(blocked_active_codes)}",
            "trigger_input_active": trigger_active,
            "blocked_inputs": blocked_active_codes,
            "follow_on": False,
            "pulse_seconds": 0,
            "follow_mode": True,
        }

    if manual:
        if blocked_active_codes:
            _clear_trigger_input_override(trigger_code)
            add_event("WARN", f"{rule_key} bloqueado por {', '.join(blocked_active_codes)}", 1)
            return {
                "executed": False,
                "reason": f"Bloqueado por entradas activas: {', '.join(blocked_active_codes)}",
                "trigger_input_active": trigger_active,
                "blocked_inputs": blocked_active_codes,
                "follow_on": False,
                "pulse_seconds": 0,
                "follow_mode": True,
            }
        _pulse_apply_deactivate_outputs(rule, apply_outputs_to_hardware, rule_key=rule_key)
        _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, True, rule_key=rule_key)
        runtime["last_follow_on"] = True
        runtime["last_trigger_active"] = trigger_active
        runtime["last_executed_at"] = datetime.now().isoformat()
        add_event("OK", f"Seguimiento radar (manual): ON {rule_key}", 1)
        return {
            "executed": True,
            "mode": current_mode,
            "trigger_input_active": trigger_active,
            "blocked_inputs": blocked_active_codes,
            "outputs_activated": rule.get("activate_outputs", []),
            "follow_on": True,
            "pulse_seconds": 0,
            "follow_mode": True,
            "timestamp": runtime["last_executed_at"],
        }

    runtime["last_trigger_active"] = trigger_active

    if desired and not last:
        _pulse_apply_deactivate_outputs(rule, apply_outputs_to_hardware, rule_key=rule_key)
        _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, True, rule_key=rule_key)
        runtime["last_follow_on"] = True
        runtime["last_executed_at"] = datetime.now().isoformat()
        add_event("OK", f"Radar ON → salidas regla {rule_key}", 1)
        return {
            "executed": True,
            "mode": current_mode,
            "trigger_input_active": trigger_active,
            "blocked_inputs": blocked_active_codes,
            "outputs_activated": rule.get("activate_outputs", []),
            "follow_on": True,
            "pulse_seconds": 0,
            "follow_mode": True,
            "timestamp": runtime["last_executed_at"],
        }

    if not desired and last:
        restored = _restore_temp_deactivate_outputs(
            rule, rule_key, apply_outputs_to_hardware, origin=f"radar_off:{rule_key}"
        )
        _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, False, rule_key=rule_key)
        runtime["last_follow_on"] = False
        runtime["last_executed_at"] = datetime.now().isoformat()
        add_event("INFO", f"Radar OFF o bloqueo → salidas OFF {rule_key}", 1)
        return {
            "executed": True,
            "mode": current_mode,
            "trigger_input_active": trigger_active,
            "blocked_inputs": blocked_active_codes,
            "outputs_activated": rule.get("activate_outputs", []),
            "follow_on": False,
            "pulse_seconds": 0,
            "follow_mode": True,
            "outputs_restored": restored,
            "timestamp": runtime["last_executed_at"],
        }

    return {
        "executed": False,
        "reason": "Sin cambio de nivel",
        "trigger_input_active": trigger_active,
        "follow_on": desired,
        "pulse_seconds": 0,
        "follow_mode": True,
    }


def _trigger_activated_by_panel_override(trigger_code: str, *, manual: bool = False) -> bool:
    """True si el modo se activó por panel (override ON en el trigger o ejecución manual)."""
    if manual:
        return True
    board_id, channel = _parse_in_code(trigger_code)
    return input_overrides[board_id][channel - 1] is True


def _clear_trigger_input_override(trigger_code: str) -> None:
    """Si el trigger tenía override (simulación), vuelve a REAL tras bloqueo o denegación."""
    if not isinstance(trigger_code, str) or not trigger_code.strip():
        return
    board_id, channel = _parse_in_code(trigger_code)
    if input_overrides[board_id][channel - 1] is not None:
        input_overrides[board_id][channel - 1] = None
        _persist_overrides_to_db()


def _in_code_for_board_channel(board_id: int, channel: int) -> str:
    return f"IN_{board_id:02d}_{channel:02d}"


def _blocked_inputs_for_rule(rule: dict) -> List[str]:
    return [
        code
        for code in rule.get("blocked_if_active") or []
        if _blocked_signal_active(
            code,
            use_hardware_if_no_override=True,
            use_overrides=True,
        )
    ]


def _override_request_blocked(board_id: int, channel: int, state: Optional[bool]) -> Optional[dict]:
    """Si FORZADA ON dispararía una regla bloqueada, denegar (override queda null)."""
    if state is not True:
        return None
    code = _in_code_for_board_channel(board_id, channel)
    hits: List[dict] = []
    for rk, rule in rules_config.items():
        if not rule.get("enabled", True) or not rule.get("auto_execute", True):
            continue
        if rule.get("trigger") != code:
            continue
        if not _rule_participates_in_auto_cycle(rk, rule):
            continue
        blocked = _blocked_inputs_for_rule(rule)
        if blocked:
            hits.append(
                {
                    "rule_key": rk,
                    "blocked_inputs": blocked,
                    "reason": f"Bloqueado por entradas activas: {', '.join(blocked)}",
                }
            )
    if not hits:
        return None
    return {"denied": True, "blocked_rules": hits}


def _snapshot_rule_deactivate_outputs(rule: dict, rule_key: str) -> None:
    """Guarda qué OUT de deactivate_outputs estaban ON antes de apagarlas (interruptores)."""
    _cancel_pending_temp_deactivate_restore(rule_key)
    runtime = _default_rule_runtime(rule_key)
    snap: Dict[str, bool] = {}
    for do_code in rule.get("deactivate_outputs") or []:
        try:
            b, ch = _parse_out_code(do_code)
        except HTTPException:
            continue
        if _read_output_cached(b, ch):
            snap[do_code] = True
    runtime["temp_deact_snapshot"] = snap


def _restore_snapshotted_deactivate_outputs(
    rule: dict,
    rule_key: str,
    *,
    apply_outputs_to_hardware: bool,
    origin: str,
) -> List[str]:
    """Solo vuelve a ON las salidas que estaban ON en el snapshot (interruptor OFF)."""
    runtime = _default_rule_runtime(rule_key)
    snap: Dict[str, bool] = dict(runtime.get("temp_deact_snapshot") or {})
    if not snap:
        return []
    restored: List[str] = []
    for do_code, was_on in snap.items():
        if not was_on:
            continue
        b, ch = _parse_out_code(do_code)
        _apply_output_for_rule(
            b,
            ch,
            True,
            out_code=do_code,
            origin=origin,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        )
        restored.append(do_code)
    _clear_temp_deactivate_snapshot(rule_key)
    _cancel_pending_temp_deactivate_restore(rule_key)
    if restored:
        add_event(
            "INFO",
            f"Restauradas salidas (estaban ON antes de {rule_key}): {', '.join(restored)}",
            1,
        )
    return restored


def _mark_toggle_suppress_auto_rising(rule_key: str) -> None:
    """Evita que el ciclo automático interprete un flanco espurio tras clic en el lateral."""
    _default_rule_runtime(rule_key)["suppress_auto_rising"] = True


def _apply_toggle_enclavamiento_on(
    rule_key: str,
    rule: dict,
    trigger_code: str,
    *,
    apply_outputs_to_hardware: bool,
    blocked_active_codes: List[str],
) -> dict:
    """Enciende salidas de una actuación tipo interruptor y la registra en `active_toggle_rules`."""
    global active_toggle_rules
    origin_tag = f"toggle_on:{rule_key}"
    _snapshot_rule_deactivate_outputs(rule, rule_key)
    skipped_disconnected: List[str] = []
    for do_code in rule.get("activate_outputs", []):
        board_id, channel = _parse_out_code(do_code)
        if not _apply_output_for_rule(
            board_id,
            channel,
            True,
            out_code=do_code,
            origin=origin_tag,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        ):
            skipped_disconnected.append(do_code)
    _apply_deactivate_outputs(
        rule, apply_outputs_to_hardware, rule_key=rule_key, origin=origin_tag
    )
    active_toggle_rules.add(rule_key)
    _notify_toggle_rules_changed()
    rt = rules_runtime.setdefault(
        rule_key,
        {
            "last_trigger_active": False,
            "last_executed_at": None,
            "pulse_until": None,
            "last_follow_on": False,
        },
    )
    rt["last_executed_at"] = datetime.now().isoformat()
    rt["last_trigger_active"] = True
    _mark_toggle_suppress_auto_rising(rule_key)
    add_event("OK", f"Actuación interruptor ON: {rule_key}", 1)
    return {
        "executed": True,
        "toggle_active": True,
        "toggle_action": "on",
        "mode": current_mode,
        "trigger_input_active": True,
        "blocked_inputs": blocked_active_codes,
        "outputs_activated": rule.get("activate_outputs", []),
        "outputs_deactivated": rule.get("deactivate_outputs", []),
        "outputs_skipped_disconnected": skipped_disconnected,
        "timestamp": rt["last_executed_at"],
    }


def _apply_toggle_enclavamiento_off(
    rule_key: str,
    rule: dict,
    *,
    apply_outputs_to_hardware: bool,
    blocked_active_codes: Optional[List[str]] = None,
) -> dict:
    """Apaga solo las salidas que encendió la regla; no re-activa las que apagó al encender."""
    global active_toggle_rules
    origin_tag = f"toggle_off:{rule_key}"
    _restore_snapshotted_deactivate_outputs(
        rule, rule_key, apply_outputs_to_hardware=apply_outputs_to_hardware, origin=origin_tag
    )
    for out_code in rule.get("activate_outputs", []):
        b, ch = _parse_out_code(out_code)
        _apply_output_for_rule(
            b,
            ch,
            False,
            out_code=out_code,
            origin=origin_tag,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        )
    trigger_code = rule.get("trigger")
    if isinstance(trigger_code, str) and trigger_code:
        mode_latches[trigger_code] = False
        _clear_trigger_input_override(trigger_code)
    active_toggle_rules.discard(rule_key)
    _persist_overrides_to_db()
    _notify_toggle_rules_changed()
    rt = rules_runtime.setdefault(
        rule_key,
        {
            "last_trigger_active": False,
            "last_executed_at": None,
            "pulse_until": None,
            "last_follow_on": False,
        },
    )
    rt["last_executed_at"] = datetime.now().isoformat()
    rt["last_trigger_active"] = False
    _mark_toggle_suppress_auto_rising(rule_key)
    add_event("OK", f"Actuación interruptor OFF: {rule_key}", 1)
    return {
        "executed": True,
        "toggle_active": False,
        "toggle_action": "off",
        "mode": current_mode,
        "blocked_inputs": blocked_active_codes or [],
        "outputs_activated": [],
        "outputs_deactivated": [],
        "timestamp": rt["last_executed_at"],
    }


def _evaluate_toggle_enclavamiento_rule(
    rule_key: str,
    rule: dict,
    *,
    use_hardware_if_no_override: bool = True,
    use_overrides: bool = True,
    apply_outputs_to_hardware: bool = True,
) -> dict:
    """Interruptor por flanco: 1ª pulsación ON, 2ª OFF (sin soltar = mantener estado)."""
    phy_in = bool(settings.panel_rules_triggers_use_physical_inputs)
    runtime = rules_runtime.setdefault(
        rule_key,
        {
            "last_trigger_active": False,
            "last_executed_at": None,
            "pulse_until": None,
            "last_follow_on": False,
        },
    )
    runtime.setdefault("pulse_until", None)
    runtime.setdefault("last_follow_on", False)
    trigger_code = rule.get("trigger", "IN_01_01")
    trigger_active = _read_input_effective(
        trigger_code,
        use_hardware_if_no_override=use_hardware_if_no_override,
        use_overrides=use_overrides,
        physical_inputs=phy_in,
    )
    blocked_active_codes = [
        code
        for code in rule.get("blocked_if_active", [])
        if _blocked_signal_active(
            code,
            use_hardware_if_no_override=use_hardware_if_no_override,
            use_overrides=use_overrides,
            physical_inputs=phy_in,
        )
    ]
    if runtime.pop("suppress_auto_rising", False):
        runtime["last_trigger_active"] = trigger_active
        return {
            "executed": False,
            "reason": "Flanco ignorado tras acción en panel",
            "trigger_input_active": trigger_active,
            "toggle_active": rule_key in active_toggle_rules,
        }
    rising_edge = trigger_active and not runtime["last_trigger_active"]
    runtime["last_trigger_active"] = trigger_active
    if not rising_edge:
        return {
            "executed": False,
            "reason": "Sin flanco de subida en interruptor",
            "trigger_input_active": trigger_active,
            "toggle_active": rule_key in active_toggle_rules,
        }
    if blocked_active_codes:
        _clear_trigger_input_override(trigger_code)
        add_event("WARN", f"{rule_key} bloqueado por {', '.join(blocked_active_codes)}", 1)
        return {
            "executed": False,
            "reason": f"Bloqueado por entradas activas: {', '.join(blocked_active_codes)}",
            "trigger_input_active": trigger_active,
            "blocked_inputs": blocked_active_codes,
            "toggle_active": rule_key in active_toggle_rules,
        }
    if rule_key in active_toggle_rules:
        return _apply_toggle_enclavamiento_off(
            rule_key,
            rule,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
            blocked_active_codes=blocked_active_codes,
        )
    return _apply_toggle_enclavamiento_on(
        rule_key,
        rule,
        trigger_code,
        apply_outputs_to_hardware=apply_outputs_to_hardware,
        blocked_active_codes=blocked_active_codes,
    )


def _apply_enclavamiento_mode_activation(
    rule: dict,
    trigger_code: str,
    *,
    activated_by_panel_override: bool,
) -> None:
    """
    Tras activar un modo enclavamiento (prioridad = último current_mode asignado):
    - hardware: override null en trigger y deactivate_modes (estado real en panel).
    - panel: override ON en trigger y OFF en deactivate_modes.
    """
    tb, tch = _parse_in_code(trigger_code)
    mode_latches.setdefault(trigger_code, False)
    mode_latches[trigger_code] = True
    if activated_by_panel_override:
        input_overrides[tb][tch - 1] = True
    else:
        input_overrides[tb][tch - 1] = None
    for code in rule.get("deactivate_modes", []):
        mode_latches.setdefault(code, False)
        mode_latches[code] = False
        board_id, channel = _parse_in_code(code)
        input_overrides[board_id][channel - 1] = (
            False if activated_by_panel_override else None
        )


def _evaluate_trigger_rule(
    rule_key: str,
    manual: bool = False,
    use_hardware_if_no_override: bool = True,
    use_overrides: bool = True,
    apply_outputs_to_hardware: bool = True,
) -> dict:
    global current_mode
    phy_in = bool(settings.panel_rules_triggers_use_physical_inputs)
    rule = rules_config.get(rule_key)
    if not rule:
        return {"executed": False, "reason": f"Regla no encontrada: {rule_key}"}
    if not manual and not _rule_participates_in_auto_cycle(rule_key, rule):
        return {
            "executed": False,
            "reason": "Regla no aplica al modo operativo actual",
            "current_mode": current_mode,
            "rule_key": rule_key,
        }
    if rule.get("type") == PULSE_5_SG_TYPE:
        return _evaluate_pulse_5_sg_rule(
            rule_key,
            manual=manual,
            use_hardware_if_no_override=use_hardware_if_no_override,
            use_overrides=use_overrides,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
            physical_inputs=phy_in,
        )
    if _is_toggle_enclavamiento_rule(rule_key, rule) and not manual:
        return _evaluate_toggle_enclavamiento_rule(
            rule_key,
            rule,
            use_hardware_if_no_override=use_hardware_if_no_override,
            use_overrides=use_overrides,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        )
    if rule_key not in rules_runtime:
        rules_runtime[rule_key] = {
            "last_trigger_active": False,
            "last_executed_at": None,
            "pulse_until": None,
            "last_follow_on": False,
        }
    else:
        rules_runtime[rule_key].setdefault("pulse_until", None)
        rules_runtime[rule_key].setdefault("last_follow_on", False)
    runtime = rules_runtime[rule_key]

    if not rule.get("enabled", True):
        return {"executed": False, "reason": "Regla deshabilitada"}

    trigger_code = rule.get("trigger", "IN_01_01")
    trigger_active = _read_input_effective(
        trigger_code,
        use_hardware_if_no_override=use_hardware_if_no_override,
        use_overrides=use_overrides,
        physical_inputs=phy_in,
    )
    blocked_codes = rule.get("blocked_if_active", [])
    blocked_active_codes = [
        code
        for code in blocked_codes
        if _blocked_signal_active(
            code,
            use_hardware_if_no_override=use_hardware_if_no_override,
            use_overrides=use_overrides,
            physical_inputs=phy_in,
        )
    ]

    if not manual:
        rising_edge = trigger_active and not runtime["last_trigger_active"]
        runtime["last_trigger_active"] = trigger_active
        if not rising_edge:
            return {"executed": False, "reason": "Sin flanco de subida en trigger", "trigger_input_active": trigger_active}
    elif not trigger_active:
        return {"executed": False, "reason": f"No se ejecuta: {trigger_code} no está activa", "trigger_input_active": False}

    if blocked_active_codes:
        _clear_trigger_input_override(trigger_code)
        add_event("WARN", f"{rule_key} bloqueado por {', '.join(blocked_active_codes)}", 1)
        return {
            "executed": False,
            "reason": f"Bloqueado por entradas activas: {', '.join(blocked_active_codes)}",
            "trigger_input_active": trigger_active,
            "blocked_inputs": blocked_active_codes,
        }

    by_panel = _trigger_activated_by_panel_override(trigger_code, manual=manual)
    _apply_enclavamiento_mode_activation(
        rule, trigger_code, activated_by_panel_override=by_panel
    )
    if _rule_owns_operational_mode(rule, rule_key):
        if _rule_is_emergency_operational(rule_key):
            _stash_operational_mode_before_emergency()
        current_mode = rule_key
        _persist_current_mode_to_db()
        _coce_notify("mode_changed", {"current_mode": current_mode})
        _zaguan_mode_changed(current_mode)
    _persist_overrides_to_db()

    origin_tag = f"enclavamiento:{rule_key}"
    skipped_disconnected: List[str] = []
    for do_code in rule.get("activate_outputs", []):
        board_id, channel = _parse_out_code(do_code)
        if not _apply_output_for_rule(
            board_id,
            channel,
            True,
            out_code=do_code,
            origin=origin_tag,
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        ):
            skipped_disconnected.append(do_code)
    _apply_deactivate_outputs(
        rule, apply_outputs_to_hardware, rule_key=rule_key, origin=origin_tag
    )

    runtime["last_executed_at"] = datetime.now().isoformat()
    add_event("OK", f"Regla ejecutada: {rule_key}", 1)
    return {
        "executed": True,
        "mode": current_mode,
        "trigger_input_active": trigger_active,
        "blocked_inputs": blocked_active_codes,
        "deactivated_modes": rule.get("deactivate_modes", []),
        "outputs_activated": rule.get("activate_outputs", []),
        "outputs_deactivated": rule.get("deactivate_outputs", []),
        "deactivate_outputs_temporary": _rule_deactivate_outputs_temporary(rule),
        "outputs_skipped_disconnected": skipped_disconnected,
        "timestamp": runtime["last_executed_at"],
    }


def _evaluate_horario_automatico(
    manual: bool = False,
    use_hardware_if_no_override: bool = True,
    apply_outputs_to_hardware: bool = True,
) -> dict:
    """Compatibilidad: misma lógica que la regla `horario_automatico` si existe."""
    if "horario_automatico" not in rules_config:
        return {"executed": False, "reason": "No hay regla horario_automatico"}
    return _evaluate_trigger_rule(
        "horario_automatico",
        manual=manual,
        use_hardware_if_no_override=use_hardware_if_no_override,
        apply_outputs_to_hardware=apply_outputs_to_hardware,
    )


def _evaluate_auto_rules(*, use_hardware_if_no_override: bool = True) -> None:
    for rk, rule in rules_config.items():
        if not rule.get("enabled", True):
            continue
        if not rule.get("auto_execute", True):
            continue
        if rule.get("type") not in AUTO_RULE_TYPES:
            continue
        if not _rule_participates_in_auto_cycle(rk, rule):
            continue
        try:
            _evaluate_trigger_rule(
                rk,
                manual=False,
                use_hardware_if_no_override=use_hardware_if_no_override,
            )
        except Exception as e:  # noqa: BLE001
            add_event("ERR", f"Error auto-evaluando {rk}: {e}", 1)


def _deactivate_rule_on_fall(
    rule_key: str,
    *,
    use_hardware_if_no_override: bool = True,
    use_overrides: bool = False,
    apply_outputs_to_hardware: bool = True,
) -> bool:
    """Desactiva la regla actual si su trigger cayó (flanco de bajada)."""
    global current_mode
    rule = rules_config.get(rule_key)
    if not rule:
        return False
    if rule.get("type") != "enclavamiento" or not rule.get("enabled", True):
        return False
    if _is_toggle_enclavamiento_rule(rule_key, rule):
        return False
    runtime = rules_runtime.setdefault(
        rule_key,
        {"last_trigger_active": False, "last_executed_at": None, "pulse_until": None, "last_follow_on": False},
    )
    runtime.setdefault("pulse_until", None)
    runtime.setdefault("last_follow_on", False)
    trigger_code = rule.get("trigger")
    if not isinstance(trigger_code, str) or not trigger_code:
        return False
    trigger_active = _read_input_effective(
        trigger_code,
        use_hardware_if_no_override=use_hardware_if_no_override,
        use_overrides=use_overrides,
        physical_inputs=bool(settings.panel_rules_triggers_use_physical_inputs),
    )
    runtime["last_trigger_active"] = trigger_active
    if trigger_active:
        return False
    if current_mode != rule_key:
        return False

    mode_latches[trigger_code] = False

    if _rule_is_emergency_operational(rule_key):
        _restore_operational_mode_after_emergency()
    else:
        current_mode = None
        _persist_current_mode_to_db()
        _coce_notify("mode_changed", {"current_mode": None})
        _zaguan_mode_changed(None)

    _restore_temp_deactivate_outputs(
        rule, rule_key, apply_outputs_to_hardware, origin=f"desactiva_flanco:{rule_key}"
    )

    # Al desactivar por flanco OFF, soltamos las salidas que activó esta regla.
    for out_code in rule.get("activate_outputs", []):
        b, ch = _parse_out_code(out_code)
        _apply_output_for_rule(
            b,
            ch,
            False,
            out_code=out_code,
            origin=f"desactiva_flanco:{rule_key}",
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        )

    add_event("INFO", f"Modo desactivado por trigger OFF: {rule_key}", 1)
    return True


def background_auto_rules_cycle(*, deactivate_on_fall: bool = True) -> dict:
    """
    Ciclo autónomo de backend:
    - refresca IO real de placas conectadas (lectura Modbus con lock por placa en TCP)
    - evalúa reglas usando ese snapshot (`use_hardware_if_no_override=False`) para no repetir
      `_read_all_io` por cada regla (en RTU multiplica tráfico serie y satura el bus / CPU).
    - opcional: desactiva regla activa al caer su trigger
    """
    global background_auto_rules_last_run_at
    global background_auto_rules_last_result
    global background_auto_rules_last_error
    checked = 0
    executed = 0
    deactivated = 0
    errors = 0
    error_messages: List[str] = []
    blocked_rules: List[dict] = []
    for board_id in _module_ids():
        if board_id in io_state and io_state[board_id]["connected"]:
            with _board_modbus_lock(board_id):
                _read_all_io(board_id, _modbus_lock_held=True)
    pending_restores = _process_pending_temp_deactivate_restores(
        apply_outputs_to_hardware=True
    )
    pending_mode_result = _try_execute_pending_manual_enclavamiento(
        apply_outputs_to_hardware=True
    )
    for rk, rule in rules_config.items():
        if not rule.get("enabled", True):
            continue
        if not rule.get("auto_execute", True):
            continue
        if rule.get("type") not in AUTO_RULE_TYPES:
            continue
        if not _rule_participates_in_auto_cycle(rk, rule):
            continue
        checked += 1
        try:
            result = _evaluate_trigger_rule(
                rk,
                manual=False,
                use_hardware_if_no_override=False,
                use_overrides=True,
                apply_outputs_to_hardware=True,
            )
            if result.get("executed"):
                executed += 1
                _zaguan_rule_executed(rk, result)
            elif result.get("blocked_inputs") and "Bloqueado" in (
                result.get("reason") or ""
            ):
                blocked_rules.append(
                    {
                        "rule_key": rk,
                        "blocked_inputs": list(result.get("blocked_inputs") or []),
                        "reason": result.get("reason"),
                    }
                )
            if deactivate_on_fall and _deactivate_rule_on_fall(
                rk,
                use_hardware_if_no_override=False,
                use_overrides=True,
                apply_outputs_to_hardware=True,
            ):
                deactivated += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            error_messages.append(f"{rk}: {e}")
            add_event("ERR", f"Error ciclo auto background {rk}: {e}", 1)
    result = {
        "checked_rules": checked,
        "executed_rules": executed,
        "deactivated_rules": deactivated,
        "pending_temp_restores": pending_restores,
        "pending_mode_executed": bool(
            pending_mode_result and pending_mode_result.get("executed")
        ),
        "pending_manual_mode": pending_manual_enclavamiento_mode,
        "errors": errors,
        "error_messages": error_messages[:10],
        "blocked_rules": blocked_rules[:20],
        "timestamp": datetime.now().isoformat(),
    }
    background_auto_rules_last_run_at = result["timestamp"]
    background_auto_rules_last_result = result
    background_auto_rules_last_error = error_messages[0] if error_messages else None
    return result


@router.get("/auto-rules/background-state")
def get_background_auto_rules_state():
    return {
        "enabled": bool(settings.auto_rules_background_enabled),
        "interval_seconds": float(settings.auto_rules_background_interval_seconds),
        "deactivate_on_fall": bool(settings.auto_rules_deactivate_on_fall),
        "last_run_at": background_auto_rules_last_run_at,
        "last_result": background_auto_rules_last_result,
        "last_error": background_auto_rules_last_error,
        "current_mode": current_mode,
    }


def _execute_rule_forced(rule_key: str, apply_outputs_to_hardware: bool = True) -> dict:
    """
    Ejecuta una regla JSON de forma forzada:
    - trigger por override=True
    - deactivate_modes por override=False
    - aplica salidas de activate_outputs/deactivate_outputs
    """
    global current_mode
    rule = rules_config.get(rule_key)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Regla no encontrada: {rule_key}")
    if not rule.get("enabled", True):
        return {"executed": False, "reason": "Regla deshabilitada", "rule": rule_key}

    # Incluso en ejecución forzada, respetar bloqueos por entradas activas (IN según panel_rules_triggers_use_physical_inputs).
    blocked_active_codes = _blocked_active_codes_for_rule(rule)
    if blocked_active_codes:
        add_event("WARN", f"{rule_key} bloqueado por {', '.join(blocked_active_codes)}", 1)
        if _rule_eligible_for_manual_queue(rule_key, rule):
            _set_pending_manual_enclavamiento(rule_key, blocked_active_codes)
            return {
                "executed": False,
                "queued": True,
                "pending_manual_mode": rule_key,
                "rule": rule_key,
                "reason": f"Bloqueado por entradas activas: {', '.join(blocked_active_codes)}",
                "blocked_inputs": blocked_active_codes,
            }
        return {
            "executed": False,
            "rule": rule_key,
            "reason": f"Bloqueado por entradas activas: {', '.join(blocked_active_codes)}",
            "blocked_inputs": blocked_active_codes,
        }

    _clear_pending_manual_enclavamiento()

    if rule.get("type") == PULSE_5_SG_TYPE:
        trigger_code = rule.get("trigger") or "IN_01_01"
        _apply_enclavamiento_mode_activation(
            rule, trigger_code, activated_by_panel_override=True
        )
        _pulse_apply_deactivate_outputs(rule, apply_outputs_to_hardware, rule_key=rule_key)
        _pulse_apply_activate_outputs(rule, apply_outputs_to_hardware, True, rule_key=rule_key)
        rt = _default_rule_runtime(rule_key)
        secs = _pulse_seconds(rule)
        rt["pulse_until"] = None
        rt["last_follow_on"] = secs <= 0
        rt["last_executed_at"] = datetime.now().isoformat()
        if secs > 0:
            rt["pulse_until"] = (datetime.now() + timedelta(seconds=secs)).isoformat()
            rt["pulse_trigger_panel_override"] = True
            _persist_overrides_to_db()
            add_event("OK", f"Pulso forzado {secs}s: {rule_key}", 1)
            return {
                "executed": True,
                "rule": rule_key,
                "trigger": rule.get("trigger"),
                "deactivate_modes": rule.get("deactivate_modes", []),
                "outputs_activated": rule.get("activate_outputs", []),
                "outputs_deactivated": rule.get("deactivate_outputs", []),
                "outputs_skipped_disconnected": [],
                "pulse_seconds": secs,
                "pulse_until": rt["pulse_until"],
                "follow_mode": False,
                "mode": current_mode,
            }
        _persist_overrides_to_db()
        add_event("OK", f"Seguimiento radar forzado ON: {rule_key}", 1)
        return {
            "executed": True,
            "rule": rule_key,
            "trigger": rule.get("trigger"),
            "deactivate_modes": rule.get("deactivate_modes", []),
            "outputs_activated": rule.get("activate_outputs", []),
            "outputs_deactivated": rule.get("deactivate_outputs", []),
            "outputs_skipped_disconnected": [],
            "pulse_seconds": 0,
            "follow_on": True,
            "follow_mode": True,
            "mode": current_mode,
        }

    if _is_toggle_enclavamiento_rule(rule_key, rule):
        if rule_key in active_toggle_rules:
            result = _apply_toggle_enclavamiento_off(
                rule_key, rule, apply_outputs_to_hardware=apply_outputs_to_hardware
            )
        else:
            trigger_code = rule.get("trigger") or "IN_01_01"
            result = _apply_toggle_enclavamiento_on(
                rule_key,
                rule,
                trigger_code,
                apply_outputs_to_hardware=apply_outputs_to_hardware,
                blocked_active_codes=blocked_active_codes,
            )
        result["rule"] = rule_key
        result["trigger"] = rule.get("trigger")
        return result

    trigger_code = rule.get("trigger") or "IN_01_01"
    _apply_enclavamiento_mode_activation(
        rule, trigger_code, activated_by_panel_override=True
    )

    skipped_disconnected: List[str] = []
    for out_code in rule.get("activate_outputs", []):
        b, ch = _parse_out_code(out_code)
        if not _apply_output_for_rule(
            b,
            ch,
            True,
            out_code=out_code,
            origin=f"forzado:{rule_key}",
            apply_outputs_to_hardware=apply_outputs_to_hardware,
        ):
            skipped_disconnected.append(out_code)

    _apply_deactivate_outputs(
        rule, apply_outputs_to_hardware, rule_key=rule_key, origin=f"forzado:{rule_key}"
    )

    if _rule_owns_operational_mode(rule, rule_key):
        if _rule_is_emergency_operational(rule_key):
            _stash_operational_mode_before_emergency()
        current_mode = rule_key
        _persist_current_mode_to_db()
        _coce_notify("mode_changed", {"current_mode": current_mode})
        _zaguan_mode_changed(current_mode)
    _persist_overrides_to_db()
    if rule_key in rules_runtime:
        rules_runtime[rule_key]["last_executed_at"] = datetime.now().isoformat()
    if skipped_disconnected:
        add_event(
            "INFO",
            f"Modo {rule_key}: salidas omitidas en placas desconectadas (estado en RAM): "
            f"{', '.join(skipped_disconnected)}",
            1,
        )
        _publish_panel_status_debounced(force=True)
    add_event("OK", f"Regla forzada ejecutada: {rule_key}", 1)
    out = {
        "executed": True,
        "rule": rule_key,
        "trigger": trigger_code,
        "deactivate_modes": rule.get("deactivate_modes", []),
        "outputs_activated": rule.get("activate_outputs", []),
        "outputs_deactivated": rule.get("deactivate_outputs", []),
        "outputs_skipped_disconnected": skipped_disconnected,
        "mode": current_mode,
    }
    _zaguan_rule_executed(rule_key, out)
    return out


class BoardConfig(BaseModel):
    """Actualización parcial: solo se persisten campos enviados en el JSON (evita slave_id=1 por defecto al omitirlo)."""

    host: Optional[str] = None
    port: Optional[int] = None
    slave_id: Optional[int] = None
    name: Optional[str] = None


class ChannelAction(BaseModel):
    channel: int
    state: bool


class BitmaskAction(BaseModel):
    channels_on: List[int]


class InputOverrideAction(BaseModel):
    board_id: int
    channel: int
    state: bool


class RulesUpdateBody(BaseModel):
    rules: Dict[str, dict]


class ModuleCreateBody(BaseModel):
    name: str
    host: str
    port: int = 502
    slave_id: int = 1


class ModuleUpdateBody(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    slave_id: Optional[int] = None
    sort_order: Optional[int] = None
    bitmask_address: Optional[int] = None
    relation_register: Optional[int] = None


class ChannelCreateBody(BaseModel):
    kind: str
    address: int
    slot_index: Optional[int] = None
    label: Optional[str] = None
    channel_name: Optional[str] = None
    open_cmd: Optional[int] = None
    close_cmd: Optional[int] = None


class ChannelPatchBody(BaseModel):
    slot_index: Optional[int] = None
    label: Optional[str] = None
    channel_name: Optional[str] = None
    address: Optional[int] = None
    open_cmd: Optional[int] = None
    close_cmd: Optional[int] = None
    pulse_limit: Optional[int] = None


class BulkCommandPair(BaseModel):
    address: int
    value: int


class BulkCommandsBody(BaseModel):
    all_on: Optional[BulkCommandPair] = None
    all_off: Optional[BulkCommandPair] = None


class InOutAssociationBody(BaseModel):
    """True = acople IN↔OUT (típ. valor 1 en holding); False = desacople (0)."""

    associated: bool


def _ensure_serial_client_connected() -> ModbusSerialClient:
    """Abre (o reutiliza) el cliente serial para diagnósticos RTU."""
    global serial_client
    if serial_client is None:
        serial_client = ModbusSerialClient(
            port=settings.modbus_serial_port,
            baudrate=settings.modbus_serial_baudrate,
            bytesize=settings.modbus_serial_bytesize,
            parity=settings.modbus_serial_parity,
            stopbits=settings.modbus_serial_stopbits,
            **_pymodbus_client_kwargs(),
        )
    if not _client_is_open(serial_client):
        ok = serial_client.connect()
        if not ok:
            raise RuntimeError(f"No se pudo abrir puerto serial {settings.modbus_serial_port}")
    return serial_client


@router.get("/")
def root():
    return {"service": "ETD8A12 Panel API", "status": "running", "timestamp": datetime.now().isoformat()}


@router.get("/status")
def get_status(
    run_auto_rules: bool = False,
    refresh_hardware: bool = Query(
        True,
        description="Si false, no hace lecturas Modbus (respuesta rápida; estado I/O puede estar desactualizado).",
    ),
):
    cfg_map = pms.get_boards_config_map()
    if refresh_hardware:
        # Lectura por placa con lock independiente (TCP): una placa lenta no bloquea las demás.
        for board_id in _module_ids():
            if board_id in io_state and io_state[board_id]["connected"]:
                with _board_modbus_lock(board_id):
                    _read_all_io(board_id, _modbus_lock_held=True)
    if run_auto_rules:
        # Si ya se refrescó hardware arriba, no repetir Modbus por cada regla (RTU).
        _evaluate_auto_rules(use_hardware_if_no_override=not refresh_hardware)
    elif refresh_hardware:
        _try_execute_pending_manual_enclavamiento(apply_outputs_to_hardware=True)
    payload = _build_status_payload()
    payload["auto_rules_executed"] = run_auto_rules
    return payload


@router.post("/boards/{board_id}/connect")
def connect_board(board_id: int):
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail=f"Módulo {board_id} no encontrado")
    ok = _connect_board(board_id)
    if ok:
        _read_all_io(board_id)
    connected = io_state[board_id]["connected"]
    _coce_notify(
        "board_connected",
        {"board_id": board_id, "connected": connected},
    )
    return {"board_id": board_id, "connected": connected, "state": io_state[board_id]}


@router.get("/diagnostics/rtu-ping")
def rtu_ping(
    board_id: Optional[int] = None,
    slave_ids: str = "",
    retries: int = 1,
    timeout_s: float = 1.5,
):
    """
    Diagnóstico de bus RS-485 / Modbus RTU.
    - Si no se envía `slave_ids`, usa los slave_id configurados en BD.
    - Si se envía `board_id`, usa el registro de probe de ese módulo.
    - Si `MODBUS_MODE != rtu`, devuelve error 400.
    """
    if not _is_rtu_mode():
        raise HTTPException(
            status_code=400,
            detail=f"Diagnóstico RTU requiere MODBUS_MODE=rtu (actual: {_modbus_mode()})",
        )

    retries = max(1, min(retries, 5))
    timeout_s = max(0.2, min(timeout_s, 5.0))
    cfg_map = pms.get_boards_config_map()
    mids = _module_ids()
    if not mids:
        raise HTTPException(status_code=400, detail="No hay módulos configurados")

    # Si no indican módulo, se usa el primero para calcular dirección de probe.
    probe_board_id = board_id if board_id is not None else mids[0]
    if probe_board_id not in cfg_map:
        raise HTTPException(status_code=404, detail=f"Módulo {probe_board_id} no existe")
    probe_addr = _probe_register_address(probe_board_id)

    if slave_ids.strip():
        try:
            candidates = [int(x.strip()) for x in slave_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="slave_ids debe ser CSV numérico, ej: 1,2,3") from None
    else:
        candidates = []
        for mid in mids:
            sid = int(cfg_map[mid]["slave_id"])
            if sid not in candidates:
                candidates.append(sid)

    if not candidates:
        raise HTTPException(status_code=400, detail="No hay slave_ids para probar")

    report: List[Dict[str, Any]] = []
    # Cliente temporal para diagnóstico: evita quedarse bloqueado por el cliente compartido.
    client = ModbusSerialClient(
        port=settings.modbus_serial_port,
        baudrate=settings.modbus_serial_baudrate,
        bytesize=settings.modbus_serial_bytesize,
        parity=settings.modbus_serial_parity,
        stopbits=settings.modbus_serial_stopbits,
        timeout=timeout_s,
    )
    try:
        if not client.connect():
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo abrir puerto serial {settings.modbus_serial_port}",
            )

        for sid in candidates:
            ok = False
            last_error: Optional[str] = None
            for _ in range(retries):
                try:
                    resp = client.read_holding_registers(address=probe_addr, count=1, device_id=sid)
                    if resp.isError():
                        last_error = str(resp)
                        continue
                    ok = True
                    last_error = None
                    break
                except Exception as e:  # noqa: BLE001
                    last_error = str(e)

            report.append(
                {
                    "slave_id": sid,
                    "ok": ok,
                    "probe_address": probe_addr,
                    "error": last_error,
                }
            )
    finally:
        try:
            client.close()
        except Exception:
            pass

    return {
        "modbus_mode": _modbus_mode(),
        "serial": {
            "port": settings.modbus_serial_port,
            "baudrate": settings.modbus_serial_baudrate,
            "bytesize": settings.modbus_serial_bytesize,
            "parity": settings.modbus_serial_parity,
            "stopbits": settings.modbus_serial_stopbits,
            "timeout": timeout_s,
        },
        "probe_board_id": probe_board_id,
        "probe_address": probe_addr,
        "retries": retries,
        "results": report,
    }


@router.post("/boards/{board_id}/disconnect")
def disconnect_board(board_id: int):
    global serial_client
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    if _is_rtu_mode():
        with modbus_io_lock:
            if serial_client:
                try:
                    serial_client.close()
                except Exception:
                    pass
            serial_client = None
            for mid in _module_ids():
                clients[mid] = None
                if mid in io_state:
                    io_state[mid]["connected"] = False
                _reset_read_io_fail_streak(mid)
        add_event("WARN", "RTU desconectado manualmente (bus completo)", board_id)
    else:
        with _board_modbus_lock(board_id):
            client = clients.get(board_id)
            if client:
                try:
                    client.close()
                except Exception:
                    pass
                clients[board_id] = None
        io_state[board_id]["connected"] = False
        _reset_read_io_fail_streak(board_id)
        add_event("WARN", "Desconectado manualmente", board_id)
    _coce_notify("board_disconnected", {"board_id": board_id, "connected": False})
    return {"board_id": board_id, "connected": False}


@router.put("/boards/{board_id}/config")
def update_board_config(board_id: int, config: BoardConfig):
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    patch = config.model_dump(exclude_unset=True, exclude_none=True)
    if not patch:
        raise HTTPException(
            status_code=400,
            detail="Nada que actualizar: envía al menos host, port, slave_id o name",
        )
    pms.apply_module_update(board_id, patch)
    cfg = _board_cfg(board_id)
    add_event("INFO", f"Config actualizada: {cfg['host']}:{cfg['port']} slave={cfg['slave_id']}", board_id)
    return {
        "board_id": board_id,
        "config": {
            "name": cfg["name"],
            "host": cfg["host"],
            "port": cfg["port"],
            "slave_id": cfg["slave_id"],
            "modbus_mode": _modbus_mode(),
            "serial_port": settings.modbus_serial_port if _is_rtu_mode() else None,
        },
    }


@router.post("/boards/{board_id}/output")
def set_output(
    board_id: int,
    action: ChannelAction,
    force: bool = Query(
        False,
        description="Si true y la placa está offline, actualiza solo el estado en RAM (sin Modbus).",
    ),
):
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail=f"Módulo {board_id} no encontrado")
    _, outs = pms.get_channels_for_module(board_id)
    if not 1 <= action.channel <= len(outs):
        raise HTTPException(status_code=400, detail=f"Canal debe estar entre 1 y {len(outs)}")

    connected = bool(io_state.get(board_id, {}).get("connected"))
    if not connected:
        if not force:
            raise HTTPException(status_code=503, detail=f"Módulo {board_id} no conectado")
        io_state[board_id]["outputs"][action.channel - 1] = action.state
        add_event(
            "WARN",
            f"CH{action.channel:02d} -> {'ON' if action.state else 'OFF'} "
            f"(force RAM, placa {board_id} sin Modbus)",
            board_id,
        )
        _coce_notify(
            "output_changed",
            {
                "board_id": board_id,
                "channel": action.channel,
                "state": action.state,
                "forced_ram": True,
            },
        )
        _publish_panel_status_debounced(force=True)
        return {
            "board_id": board_id,
            "channel": action.channel,
            "state": action.state,
            "hardware_written": False,
            "forced_ram": True,
        }

    client = get_client(board_id)
    cfg = _board_cfg(board_id)
    ch = outs[action.channel - 1]
    register = int(ch["address"])
    open_v = int(ch["open_cmd"]) if ch["open_cmd"] is not None else CMD_OPEN
    close_v = int(ch["close_cmd"]) if ch["close_cmd"] is not None else CMD_CLOSE
    value = open_v if action.state else close_v
    try:
        with _board_modbus_lock(board_id):
            result = client.write_register(address=register, value=value, device_id=cfg["slave_id"])
        if result.isError():
            raise HTTPException(status_code=502, detail=f"Error Modbus: {result}")
        io_state[board_id]["outputs"][action.channel - 1] = action.state
        add_event("OK", f"CH{action.channel:02d} -> {'ON' if action.state else 'OFF'}", board_id)
        _coce_notify(
            "output_changed",
            {
                "board_id": board_id,
                "channel": action.channel,
                "state": action.state,
            },
        )
        _publish_panel_status_debounced(force=True)
        return {
            "board_id": board_id,
            "channel": action.channel,
            "state": action.state,
            "hardware_written": True,
            "forced_ram": False,
        }
    except ModbusException as e:
        raise HTTPException(status_code=502, detail=f"Error Modbus: {e}")


@router.post("/boards/{board_id}/outputs/all_on")
def all_outputs_on(board_id: int):
    client = get_client(board_id)
    cfg = _board_cfg(board_id)
    bulk = pms.get_bulk_commands(board_id)
    if "all_on" not in bulk:
        raise HTTPException(status_code=400, detail="No hay comando all_on configurado para este módulo")
    addr, val = bulk["all_on"]
    with _board_modbus_lock(board_id):
        result = client.write_register(address=addr, value=val, device_id=cfg["slave_id"])
    if result.isError():
        raise HTTPException(status_code=502, detail=str(result))
    n_out = len(io_state[board_id]["outputs"])
    io_state[board_id]["outputs"] = [True] * n_out
    add_event("OK", "Todas las salidas ON", board_id)
    return {"board_id": board_id, "all_outputs": True}


@router.post("/boards/{board_id}/outputs/all_off")
def all_outputs_off(board_id: int):
    client = get_client(board_id)
    cfg = _board_cfg(board_id)
    bulk = pms.get_bulk_commands(board_id)
    if "all_off" not in bulk:
        raise HTTPException(status_code=400, detail="No hay comando all_off configurado para este módulo")
    addr, val = bulk["all_off"]
    with _board_modbus_lock(board_id):
        result = client.write_register(address=addr, value=val, device_id=cfg["slave_id"])
    if result.isError():
        raise HTTPException(status_code=502, detail=str(result))
    n_out = len(io_state[board_id]["outputs"])
    io_state[board_id]["outputs"] = [False] * n_out
    add_event("OK", "Todas las salidas OFF", board_id)
    return {"board_id": board_id, "all_outputs": False}


@router.post("/boards/{board_id}/input-output-association")
def set_input_output_association(board_id: int, body: InOutAssociationBody):
    """
    Escribe el holding configurado en `relation_register` (p. ej. 0x00FA):
    0 = desacoplado, 1 = acoplado (modo fábrica típico en ETD8A12).
    Requiere módulo conectado por Modbus (mismo criterio que salidas).
    """
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail=f"Módulo {board_id} no encontrado")
    cfg = _board_cfg(board_id)
    rel = cfg.get("relation_register")
    if rel is None:
        raise HTTPException(
            status_code=400,
            detail="relation_register no definido en BD para este módulo",
        )
    client = get_client(board_id)
    value = 1 if body.associated else 0
    sid = int(cfg["slave_id"])
    addr = int(rel)
    try:
        with _board_modbus_lock(board_id):
            result = client.write_register(address=addr, value=value, device_id=sid)
        if hasattr(result, "isError") and result.isError():
            add_event(
                "ERR",
                f"IN↔OUT asociación Modbus error en 0x{addr:04X} slave={sid} valor={value}: {result}",
                board_id,
            )
            raise HTTPException(status_code=502, detail=str(result))
        io_state[board_id]["in_out_associated"] = body.associated
        add_event(
            "OK",
            f"IN↔OUT {'acoplado' if body.associated else 'desacoplado'}: holding 0x{addr:04X} ({addr})={value}, slave_id={sid}",
            board_id,
        )
        return {"board_id": board_id, "associated": body.associated}
    except ModbusException as e:
        add_event("ERR", f"IN↔OUT asociación Modbus: {e}", board_id)
        raise HTTPException(status_code=502, detail=f"Error Modbus: {e}") from e


@router.post("/boards/{board_id}/outputs/bitmask")
def set_outputs_bitmask(board_id: int, action: BitmaskAction):
    _, outs = pms.get_channels_for_module(board_id)
    n_out = len(outs)
    for ch in action.channels_on:
        if not 1 <= ch <= n_out:
            raise HTTPException(status_code=400, detail=f"Canal {ch} inválido (1-{n_out})")
    client = get_client(board_id)
    cfg = _board_cfg(board_id)
    bm_addr = cfg.get("bitmask_address")
    if bm_addr is None:
        raise HTTPException(status_code=400, detail="Este módulo no tiene bitmask_address configurado")
    bitmask = 0
    for ch in action.channels_on:
        bitmask |= 1 << (ch - 1)
    with _board_modbus_lock(board_id):
        result = client.write_register(address=int(bm_addr), value=bitmask, device_id=cfg["slave_id"])
    if result.isError():
        raise HTTPException(status_code=502, detail=str(result))
    for i in range(n_out):
        io_state[board_id]["outputs"][i] = bool((bitmask >> i) & 1)
    add_event("OK", f"Bitmask 0x{bitmask:04X}", board_id)
    return {"board_id": board_id, "bitmask": hex(bitmask), "channels_on": sorted(action.channels_on)}


@router.get("/boards/{board_id}/inputs")
def read_inputs(board_id: int):
    client = get_client(board_id)
    cfg = _board_cfg(board_id)
    ins, _ = pms.get_channels_for_module(board_id)
    slave = cfg["slave_id"]
    values_raw: List[bool] = []
    with _board_modbus_lock(board_id):
        for ch in ins:
            res = client.read_holding_registers(address=int(ch["address"]), count=1, device_id=slave)
            if res.isError() or not res.registers:
                raise HTTPException(status_code=502, detail="Error leyendo entradas")
            values_raw.append(bool(res.registers[0]))
    prev_raw = tuple(io_state[board_id].get("inputs_raw") or [])
    io_state[board_id]["inputs_raw"] = values_raw
    values_effective = [values_raw[i] if input_overrides[board_id][i] is None else input_overrides[board_id][i] for i in range(len(values_raw))]
    io_state[board_id]["inputs"] = values_effective
    _track_input_pulse_rising_edges(board_id, prev_raw)
    return {
        "board_id": board_id,
        "inputs_raw": {f"IN{i+1}": values_raw[i] for i in range(len(values_raw))},
        "inputs_effective": {f"IN{i+1}": values_effective[i] for i in range(len(values_effective))},
        "input_overrides": {f"IN{i+1}": input_overrides[board_id][i] for i in range(len(input_overrides[board_id]))},
    }


@router.get("/boards/{board_id}/outputs")
def read_outputs(board_id: int):
    client = get_client(board_id)
    cfg = _board_cfg(board_id)
    _, outs = pms.get_channels_for_module(board_id)
    slave = cfg["slave_id"]
    values: List[bool] = []
    with _board_modbus_lock(board_id):
        for ch in outs:
            res = client.read_holding_registers(address=int(ch["address"]), count=1, device_id=slave)
            if res.isError() or not res.registers:
                raise HTTPException(status_code=502, detail="Error leyendo salidas")
            values.append(bool(res.registers[0]))
    io_state[board_id]["outputs"] = values
    return {"board_id": board_id, "outputs": {f"OUT{i+1}": values[i] for i in range(len(values))}}


@router.get("/events")
def get_events(limit: int = 300, type_filter: Optional[str] = None):
    sev = type_filter.strip().upper() if type_filter and type_filter.strip() else None
    total, rows = ses.list_events(
        severity_filter=sev,
        limit=min(limit, 2000),
        offset=0,
    )
    return {"total": total, "events": rows}


@router.delete("/events")
def clear_events():
    n = ses.clear_all_events()
    return {"ok": True, "message": "Histórico limpiado", "deleted": n}


@router.get("/inputs/override")
def get_input_overrides():
    return {
        "overrides": {
            str(board_id): {
                f"IN{i+1}": input_overrides[board_id][i] for i in range(len(input_overrides.get(board_id, [])))
            }
            for board_id in _module_ids()
            if board_id in input_overrides
        }
    }


@router.post("/inputs/override")
def set_input_override(action: InputOverrideAction):
    if not _board_exists(action.board_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    ins, _ = pms.get_channels_for_module(action.board_id)
    if not 1 <= action.channel <= len(ins):
        raise HTTPException(status_code=400, detail=f"Canal debe estar entre 1 y {len(ins)}")
    idx = action.channel - 1
    denial = _override_request_blocked(action.board_id, action.channel, action.state)
    if denial:
        input_overrides[action.board_id][idx] = None
        _persist_overrides_to_db()
        for hit in denial.get("blocked_rules") or []:
            rk = hit.get("rule_key", "regla")
            ins = ", ".join(hit.get("blocked_inputs") or [])
            add_event("WARN", f"Override IN{action.channel:02d} denegado: {rk} bloqueado por {ins}", action.board_id)
        return {
            "board_id": action.board_id,
            "channel": action.channel,
            "override": None,
            "denied": True,
            "blocked_rules": denial.get("blocked_rules"),
            "active_toggle_rules": sorted(active_toggle_rules),
        }
    input_overrides[action.board_id][idx] = action.state
    _persist_overrides_to_db()
    add_event("INFO", f"Override IN{action.channel:02d} = {action.state}", action.board_id)
    _coce_notify(
        "input_override",
        {
            "board_id": action.board_id,
            "channel": action.channel,
            "override": action.state,
        },
    )
    auto_rules: Optional[dict] = None
    if settings.auto_rules_background_enabled:
        try:
            auto_rules = background_auto_rules_cycle(
                deactivate_on_fall=bool(settings.auto_rules_deactivate_on_fall)
            )
        except Exception:  # noqa: BLE001
            pass
    return {
        "board_id": action.board_id,
        "channel": action.channel,
        "override": action.state,
        "auto_rules": auto_rules,
        "active_toggle_rules": sorted(active_toggle_rules),
    }


@router.delete("/inputs/override")
def clear_input_override(board_id: int, channel: int):
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    ins, _ = pms.get_channels_for_module(board_id)
    if not 1 <= channel <= len(ins):
        raise HTTPException(status_code=400, detail=f"Canal debe estar entre 1 y {len(ins)}")
    idx = channel - 1
    input_overrides[board_id][idx] = None
    _persist_overrides_to_db()
    add_event("INFO", f"Override IN{channel:02d} limpiado", board_id)
    _coce_notify(
        "input_override",
        {"board_id": board_id, "channel": channel, "override": None},
    )
    auto_rules: Optional[dict] = None
    if settings.auto_rules_background_enabled:
        try:
            auto_rules = background_auto_rules_cycle(
                deactivate_on_fall=bool(settings.auto_rules_deactivate_on_fall)
            )
        except Exception:  # noqa: BLE001
            pass
    return {
        "board_id": board_id,
        "channel": channel,
        "override": None,
        "auto_rules": auto_rules,
        "active_toggle_rules": sorted(active_toggle_rules),
    }


@router.get("/rules/state")
def get_rules_state():
    return {
        "current_mode": current_mode,
        "active_toggle_rules": sorted(active_toggle_rules),
        "pending_manual_enclavamiento_mode": pending_manual_enclavamiento_mode,
        "mode_latches": mode_latches,
        "rules": rules_config,
        "runtime": rules_runtime,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/rules")
def get_rules():
    return {"rules": rules_config, "runtime": rules_runtime}


@router.put("/rules")
def update_rules(body: RulesUpdateBody):
    global rules_config
    rules_config = body.rules
    _sync_mode_latches_from_rules(rules_config)
    _sync_rules_runtime(rules_config)
    _save_rules_to_disk(rules_config)
    add_event("INFO", "Reglas actualizadas por JSON", 1)
    return {"ok": True, "rules": rules_config}


@router.post("/rules/{rule_key}/run")
def run_rule_by_key(rule_key: str, simulate: bool = False):
    return _execute_rule_forced(rule_key=rule_key, apply_outputs_to_hardware=not simulate)


@router.post("/rules/horario-automatico/run")
def run_horario_automatico():
    """
    Ejecución manual forzada de "Horario Automático":
    - Fuerza IN_01_01 activa (override=True).
    - Fuerza IN_01_02..IN_01_07 desactivas (override=False).
    - Activa OUT5 y OUT6 de placa 2 y placa 3.
    """
    return _execute_rule_forced("horario_automatico", apply_outputs_to_hardware=True)


@router.get("/modules")
def list_modules_config():
    return {"modules": pms.get_full_config_for_api()}


@router.post("/modules")
def create_module_api(body: ModuleCreateBody):
    mid = pms.create_module(body.name, body.host, body.port, body.slave_id)
    _sync_runtime_from_db()
    add_event("INFO", f"Módulo creado id={mid} {body.name}", mid)
    mod = next((m for m in pms.get_full_config_for_api() if m["id"] == mid), None)
    return {"id": mid, "module": mod}


@router.put("/modules/{module_id}")
def update_module_api(module_id: int, body: ModuleUpdateBody):
    if not _board_exists(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    patch = body.model_dump(exclude_unset=True)
    if patch:
        pms.apply_module_update(module_id, patch)
    _sync_runtime_from_db()
    add_event("INFO", "Módulo actualizado en configuración", module_id)
    return {"id": module_id, "config": _board_cfg(module_id)}


@router.delete("/modules/{module_id}")
def delete_module_api(module_id: int):
    if not _board_exists(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    c = None
    with _board_modbus_lock(module_id):
        c = clients.pop(module_id, None)
        if c:
            try:
                c.close()
            except Exception:
                pass
    _drop_board_modbus_lock(module_id)
    pms.delete_module(module_id)
    _sync_runtime_from_db()
    add_event("WARN", "Módulo eliminado de la configuración", module_id)
    return {"ok": True, "id": module_id}


@router.post("/modules/{module_id}/channels")
def add_channel_api(module_id: int, body: ChannelCreateBody):
    if not _board_exists(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    cid = pms.add_channel(
        module_id,
        body.kind,
        body.address,
        slot_index=body.slot_index,
        label=body.label,
        channel_name=body.channel_name,
        open_cmd=body.open_cmd,
        close_cmd=body.close_cmd,
    )
    _sync_runtime_from_db()
    add_event("INFO", f"Canal {body.kind} id={cid} addr=0x{body.address:X}", module_id)
    return {"channel_id": cid}


@router.put("/modules/{module_id}/channels/{channel_id}")
def patch_channel_api(module_id: int, channel_id: int, body: ChannelPatchBody):
    if not _board_exists(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT module_id, kind FROM panel_module_channels WHERE id = ?",
            (channel_id,),
        ).fetchone()
    if not row or row[0] != module_id:
        raise HTTPException(status_code=404, detail="Canal no pertenece a este módulo")
    patch = body.model_dump(exclude_unset=True)
    if "pulse_limit" in patch and row[1] != "input":
        raise HTTPException(status_code=400, detail="pulse_limit solo aplica a entradas (IN)")
    if "pulse_limit" in patch:
        pl = patch["pulse_limit"]
        if pl is not None and pl < 1:
            raise HTTPException(status_code=400, detail="pulse_limit debe ser >= 1 o null")
    pms.update_channel(
        channel_id,
        slot_index=patch.get("slot_index"),
        label=patch["label"] if "label" in patch else ...,
        channel_name=patch["channel_name"] if "channel_name" in patch else ...,
        address=patch.get("address"),
        open_cmd=patch["open_cmd"] if "open_cmd" in patch else ...,
        close_cmd=patch["close_cmd"] if "close_cmd" in patch else ...,
        pulse_limit=patch["pulse_limit"] if "pulse_limit" in patch else ...,
    )
    _sync_runtime_from_db()
    return {"ok": True, "channel_id": channel_id}


@router.post("/modules/{module_id}/channels/{channel_id}/reset-pulses")
def reset_channel_pulses_api(module_id: int, channel_id: int):
    if not _board_exists(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT module_id, kind FROM panel_module_channels WHERE id = ?",
            (channel_id,),
        ).fetchone()
    if not row or row[0] != module_id:
        raise HTTPException(status_code=404, detail="Canal no pertenece a este módulo")
    if row[1] != "input":
        raise HTTPException(status_code=400, detail="Solo entradas (IN) tienen contador de pulsaciones")
    if not pms.reset_channel_pulse_count(channel_id):
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    return {"ok": True, "channel_id": channel_id, "pulse_count": 0}


@router.delete("/modules/{module_id}/channels/{channel_id}")
def delete_channel_api(module_id: int, channel_id: int):
    if not _board_exists(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT module_id FROM panel_module_channels WHERE id = ?",
            (channel_id,),
        ).fetchone()
    if not row or row[0] != module_id:
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    pms.delete_channel(channel_id)
    _sync_runtime_from_db()
    add_event("INFO", f"Canal eliminado id={channel_id}", module_id)
    return {"ok": True}


@router.put("/modules/{module_id}/bulk")
def set_bulk_commands_api(module_id: int, body: BulkCommandsBody):
    if not _board_exists(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    if body.all_on:
        pms.set_bulk_command(module_id, "all_on", body.all_on.address, body.all_on.value)
    if body.all_off:
        pms.set_bulk_command(module_id, "all_off", body.all_off.address, body.all_off.value)
    _sync_runtime_from_db()
    add_event("INFO", "Comandos all_on / all_off actualizados", module_id)
    return {"bulk": pms.get_bulk_commands(module_id)}


@router.post("/rules/evaluate")
def evaluate_rules_now(force_trigger_override: bool = True, rule_key: Optional[str] = None):
    """
    Evalúa una regla tipo enclavamiento en modo manual (flanco / trigger).
    Si no se indica rule_key, se usa `horario_automatico` si existe; si no, la primera regla enclavamiento habilitada.
    """
    if not rules_config:
        raise HTTPException(status_code=400, detail="No hay reglas configuradas")

    rk = rule_key
    if rk is None:
        if "horario_automatico" in rules_config:
            rk = "horario_automatico"
        else:
            for cand, r in rules_config.items():
                if r.get("type") == "enclavamiento" and r.get("enabled", True):
                    rk = cand
                    break
    if rk is None or rk not in rules_config:
        raise HTTPException(status_code=400, detail="Indica rule_key o define al menos una regla enclavamiento")

    rule = rules_config[rk]
    if rule.get("type") != "enclavamiento":
        raise HTTPException(status_code=400, detail=f"La regla {rk} no es tipo enclavamiento (auto-evaluable en este endpoint)")

    if force_trigger_override:
        trigger_code = rule.get("trigger", "IN_01_01")
        if trigger_code:
            b, ch = _parse_in_code(trigger_code)
            input_overrides[b][ch - 1] = True
            _persist_overrides_to_db()
            add_event("INFO", f"Evaluate: trigger {trigger_code} forzado por override", b)

    result = _evaluate_trigger_rule(
        rk,
        manual=True,
        use_hardware_if_no_override=not force_trigger_override,
        apply_outputs_to_hardware=not force_trigger_override,
    )
    return {"ok": True, "results": {rk: result}, "rule_key": rk}


# ─── Funciones usadas por la API tablet v1 (`tablet_v1.py`) ─────────────────


def api_v1_list_modes_from_rules() -> List[Dict[str, Any]]:
    """Lista claves de reglas (modos) tal como están en `panel_rules.json`."""
    items: List[Dict[str, Any]] = []
    for key, rule in rules_config.items():
        items.append(
            {
                "key": key,
                "enabled": bool(rule.get("enabled", True)),
                "type": rule.get("type"),
                "auto_execute": rule.get("auto_execute"),
                "color": rule.get("color"),
            }
        )
    return items


def api_v1_get_current_mode() -> Optional[str]:
    return current_mode


def api_v1_get_pending_mode() -> Optional[str]:
    return pending_manual_enclavamiento_mode


def api_v1_get_mode_status() -> dict:
    return {
        "current_mode": current_mode,
        "pending_mode": pending_manual_enclavamiento_mode,
    }


def api_v1_clear_current_mode_if_match(rule_key: str) -> dict:
    """Pone `current_mode` en null solo si coincide con el modo indicado."""
    global current_mode
    if current_mode != rule_key:
        return {"cleared": False, "current_mode": current_mode}
    rule = rules_config.get(rule_key) or {}
    restored: List[str] = []
    if rule:
        restored = _restore_temp_deactivate_outputs(
            rule, rule_key, True, origin=f"clear_mode:{rule_key}"
        )
        for out_code in rule.get("activate_outputs", []):
            b, ch = _parse_out_code(out_code)
            if io_state.get(b, {}).get("connected"):
                _write_output_if_connected(
                    b, ch, False, out_code=out_code, origin=f"clear_mode:{rule_key}"
                )
    current_mode = None
    _persist_current_mode_to_db()
    _coce_notify("mode_changed", {"current_mode": None})
    _zaguan_mode_changed(None)
    add_event("INFO", f"Modo desactivado vía API tablet: {rule_key}", 1)
    return {"cleared": True, "current_mode": None, "outputs_restored": restored}


def api_v1_read_input_by_code(code: str) -> bool:
    """Lectura efectiva de un IN del panel (override + snapshot IO)."""
    return _read_input_effective(
        code,
        use_hardware_if_no_override=False,
        use_overrides=True,
        physical_inputs=False,
    )


def api_v1_read_output_by_code(code: str, *, refresh: bool = True) -> bool:
    """Estado ON/OFF de una salida del panel (snapshot IO, opcional refresh Modbus)."""
    board_id, channel = _parse_out_code(code)
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail=f"Módulo {board_id} no encontrado")
    if refresh:
        if not io_state.get(board_id, {}).get("connected"):
            _connect_board(board_id)
        if io_state.get(board_id, {}).get("connected"):
            try:
                _read_all_io(board_id)
            except Exception:  # noqa: BLE001
                pass
    return _read_output_cached(board_id, channel)


def api_v1_refresh_board_io(board_id: int) -> bool:
    """Refresca entradas/salidas Modbus de una placa (p. ej. antes de leer bulones)."""
    if not _board_exists(board_id):
        return False
    if not io_state.get(board_id, {}).get("connected"):
        _connect_board(board_id)
    if not io_state.get(board_id, {}).get("connected"):
        return False
    try:
        _read_all_io(board_id)
        return True
    except Exception:  # noqa: BLE001
        return False


def api_v1_execute_rule_for_tablet(rule_key: str) -> dict:
    try:
        from app.services import zaguan_orchestrator as zo

        special = zo.execute_tablet_door_open_sync(rule_key)
        if special is not None:
            _zaguan_rule_executed(rule_key, special)
            return special
    except Exception:  # noqa: BLE001
        pass
    return _execute_rule_forced(rule_key, apply_outputs_to_hardware=True)


def api_v1_set_output_by_code(code: str, on: bool) -> dict:
    try:
        from app.services import zaguan_orchestrator as zo

        special = zo.execute_tablet_door_output_sync(code, on)
        if special is not None:
            return special
    except Exception:  # noqa: BLE001
        pass
    board_id, channel = _parse_out_code(code)
    if not _board_exists(board_id):
        raise HTTPException(status_code=404, detail=f"Módulo {board_id} no encontrado")
    st = io_state.get(board_id) or {}
    if not st.get("connected"):
        _connect_board(board_id)
    st = io_state.get(board_id) or {}
    if not st.get("connected"):
        raise HTTPException(status_code=503, detail=f"No se pudo conectar módulo {board_id}")
    _write_output(board_id, channel, on)
    add_event("OK", f"Salida (API tablet v1) {code} -> {'ON' if on else 'OFF'}", board_id)
    _coce_notify(
        "output_changed",
        {"board_id": board_id, "channel": channel, "state": on, "code": code},
    )
    result: dict = {"code": code, "on": on, "board_id": board_id, "channel": channel}
    if not on:
        try:
            from app.services import zaguan_orchestrator as zo

            door = zo.door_for_hold_output(code)
            if door is not None:
                zo.on_tablet_hold_output_released(door)
                api_v1_refresh_board_io(zo.DOOR_BOARD_ID[door])
        except Exception:  # noqa: BLE001
            pass
        pending = _try_execute_pending_manual_enclavamiento(apply_outputs_to_hardware=True)
        if pending:
            result["pending_mode_result"] = pending
    return result
