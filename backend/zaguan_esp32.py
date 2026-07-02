"""
SAIMA Seguridad — Control de Accesos Banco Santander
Módulo: zaguan_esp32.py

Endpoints que el ESP32-S3-ETH usa para:
  1. GET  /zaguan/estado         → obtener estado de canales al arrancar
  2. POST /zaguan/pulsacion/p{n} → notificar pulsación de botón

Añadir al server.py:
    from zaguan_esp32 import router as esp32_router
    app.include_router(esp32_router)
"""

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel
from typing import Any, Literal, Callable
import logging
import asyncio

from app.services import zaguan_led_client

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Tipos ──────────────────────────────────────────────────
EstadoValido = Literal["libre", "ocupado", "abriendo", "apagado"]
CanalValido  = Literal["p1", "p2", "p3", "p4"]

# ── Estado actual de los 4 canales (en memoria) ────────────
_estado_canales: dict[str, EstadoValido] = {
    "p1": "apagado",
    "p2": "apagado",
    "p3": "apagado",
    "p4": "apagado",
}

# ── Callback de pulsación ──────────────────────────────────
# Registrar desde server.py para conectar con la lógica de puertas
# Ejemplo: registrar_callback_pulsacion(mi_funcion_apertura)
_callback_pulsacion: Callable | None = None

def registrar_callback_pulsacion(fn: Callable):
    """
    Registra la función que se llamará cuando el ESP32
    notifique una pulsación de botón.

    La función debe aceptar: (canal: str, ts: int)
      canal → "p1" | "p2" | "p3" | "p4"
      ts    → timestamp millis() del ESP32

    Ejemplo en server.py:
        from zaguan_esp32 import registrar_callback_pulsacion

        async def gestionar_apertura(canal: str, ts: int):
            logger.info(f"Pulsación en canal {canal}")
            # lógica de apertura de puerta...

        registrar_callback_pulsacion(gestionar_apertura)
    """
    global _callback_pulsacion
    _callback_pulsacion = fn
    logger.info("[ESP32] Callback de pulsación registrado")


# ══════════════════════════════════════════════════════════
#  MODELOS
# ══════════════════════════════════════════════════════════

class PulsacionBody(BaseModel):
    canal: int          # 1-4
    ts:    int          # millis() del ESP32
    estado: str | None = None


class EstadoCanalBody(BaseModel):
    estado: EstadoValido


class DeviceConfigRedBody(BaseModel):
    ip: str
    gateway: str
    subnet: str
    backend_ip: str
    backend_puerto: int
    backend_ruta: str
    pulsacion_ruta: str


class DeviceConfigCanalBody(BaseModel):
    canal: int
    leds: int | None = None
    brillo: int | None = None


class DeviceConfigEstadoBody(BaseModel):
    estado: EstadoValido
    canal: int | None = None
    color: list[int] | None = None
    animacion: str | None = None
    velocidad: int | None = None


class DeviceConfigFlashBody(BaseModel):
    color: list[int] | None = None
    n_flashes: int | None = None
    duracion_ms: int | None = None


class ChannelTargetBody(BaseModel):
    host: str = ""
    port: int | None = None


class DeviceTargetBody(BaseModel):
    host: str
    port: int = 80
    timeout_s: float = 0.5
    channels: dict[str, ChannelTargetBody] | None = None


class LlaveEchadaEmulateBody(BaseModel):
    action: Literal["cerrar", "abrir", "maniobra", "real"]


# Llave WinHose: IN3 placa 2 = P1, IN3 placa 3 = P2. Cerrado=ON, abierto=OFF.
LLAVE_ECHADA_BY_ID: dict[int, dict[str, Any]] = {
    1: {
        "board_id": 2,
        "channel": 3,
        "code": "IN_02_03",
        "door": "p1",
        "label": "Llave echada 1",
        "puerta": "P1 (calle)",
    },
    2: {
        "board_id": 3,
        "channel": 3,
        "code": "IN_03_03",
        "door": "p2",
        "label": "Llave echada 2",
        "puerta": "P2 (oficina)",
    },
}


def _emulate_llave_override(board_id: int, channel: int, state: bool | None) -> None:
    from app.api.routes import panel as panel_mod
    from app.db import panel_modules_store as pms

    if board_id not in panel_mod.input_overrides:
        raise HTTPException(status_code=404, detail=f"Placa {board_id} no configurada")
    ins, _ = pms.get_channels_for_module(board_id)
    if not 1 <= channel <= len(ins):
        raise HTTPException(status_code=400, detail=f"Canal {channel} fuera de rango")
    panel_mod.input_overrides[board_id][channel - 1] = state
    panel_mod._persist_overrides_to_db()
    panel_mod.add_event(
        "INFO",
        f"Emulación llave echada: IN{channel:02d} P{board_id} → "
        f"{'REAL' if state is None else ('ON (cerrado)' if state else 'OFF (abierto)')}",
        board_id,
    )


def _poll_zaguan_after_llave_emulation() -> dict[str, Any]:
    from app.services import zaguan_orchestrator as zo

    zo.poll_winhose()
    zo.poll_door_sensors()
    return zo.get_autoservicio_status()


# ══════════════════════════════════════════════════════════
#  ENDPOINT 1 — Estado al arrancar
#  El ESP32 hace GET aquí nada más conectar
# ══════════════════════════════════════════════════════════

@router.get("/api/zaguan/estado")
@router.get("/zaguan/estado")
async def get_estado_zaguan():
    """
    El ESP32 consulta este endpoint al arrancar para obtener
    el estado real de cada canal antes de iniciar animaciones.

    Respuesta:
    {
        "p1": "libre",
        "p2": "ocupado",
        "p3": "libre",
        "p4": "apagado"
    }
    """
    out: dict[str, Any] = dict(_estado_canales)
    try:
        from app.services import zaguan_orchestrator as zo

        for ch, est in zo.get_led_states().items():
            out[ch] = est
        extra = zo.get_autoservicio_status()
        if (
            any((extra.get("winhose_libre_parpadeo") or {}).values())
            or extra.get("extendido_p2_call_pending")
            or extra.get("p3_intermittent")
        ):
            out["_autoservicio"] = extra
    except Exception:  # noqa: BLE001
        pass
    return out


@router.post("/api/zaguan/estado/{canal}")
@router.post("/zaguan/estado/{canal}")
async def set_estado_zaguan(
    canal: CanalValido = Path(..., description="Canal a actualizar: p1|p2|p3|p4"),
    body: EstadoCanalBody = None,
):
    """
    Actualiza el estado lógico de un canal en backend.
    Útil para pruebas y para sincronizar estado visual/manual.
    """
    if body is None:
        return {"ok": False, "error": "Body requerido: {estado}"}
    actualizar_estado_canal(canal, body.estado)
    return {"ok": True, "canal": canal, "estado": body.estado}


# ══════════════════════════════════════════════════════════
#  ENDPOINT 2 — Pulsaciones del ESP32
#  Un endpoint por canal — fire and forget desde el ESP32
# ══════════════════════════════════════════════════════════

@router.post("/api/zaguan/pulsacion/{canal}")
@router.post("/zaguan/pulsacion/{canal}")
async def recibir_pulsacion(
    canal: CanalValido = Path(..., description="Canal pulsado: p1|p2|p3|p4"),
    request: Request = None,
    body: PulsacionBody = None
):
    """
    El ESP32 llama a este endpoint cuando se pulsa un botón físico.
    El ESP32 dispara y se olvida — responder rápido.

    Mapeo de canales (1 ESP por canal lógico):
      p1 → P1 videoportero exterior      (192.168.1.60)
      p2 → P2 videoportero interior      (192.168.1.62)
      p3 → P1 pulsador exterior          (192.168.1.61)
      p4 → P2 pulsador interior          (192.168.1.63)
    """
    payload_raw: Any = None
    if request is not None:
        try:
            payload_raw = await request.json()
        except Exception:
            payload_raw = None
    ts = body.ts if body else (int(payload_raw.get("ts")) if isinstance(payload_raw, dict) and payload_raw.get("ts") is not None else 0)
    logger.info("[ESP32] PULSACION RECIBIDA canal=%s", canal)
    logger.info("[ESP32] Payload pulsacion: %s", payload_raw if payload_raw is not None else (body.model_dump() if body else {}))

    if _callback_pulsacion is not None:
        if asyncio.iscoroutinefunction(_callback_pulsacion):
            result = await _callback_pulsacion(canal, ts)
            if isinstance(result, dict):
                return result
        else:
            asyncio.create_task(_ejecutar_callback_pulsacion(canal, ts))

    return {"ok": True}


@router.post("/api/zaguan/pulsacion")
@router.post("/zaguan/pulsacion")
async def recibir_pulsacion_base(request: Request):
    """
    Endpoint temporal de captura genérica de payload.
    Permite inspeccionar el body real que envía el ESP32 sin asumir canal en la ruta.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    logger.info("[ESP32] PULSACION RECIBIDA (base)")
    logger.info("[ESP32] Payload pulsacion (base): %s", payload)
    return {"ok": True}


# ══════════════════════════════════════════════════════════
#  ENDPOINTS DE CLIENTE SALIENTE (backend -> ESP32)
# ══════════════════════════════════════════════════════════

@router.get("/api/zaguan/device/ping")
def device_ping(canal: CanalValido | None = Query(None)):
    try:
        return zaguan_led_client.ping(canal)
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/api/zaguan/device/ping-all")
def device_ping_all():
    return zaguan_led_client.ping_all()


@router.get("/api/zaguan/device/estado")
def device_estado(canal: CanalValido | None = Query(None)):
    try:
        if canal:
            return zaguan_led_client.estado(canal)
        return zaguan_led_client.estado_all()
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/api/zaguan/device/config")
def device_config(canal: CanalValido | None = Query(None)):
    try:
        return zaguan_led_client.config_get(canal)
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/api/zaguan/device/canal/{canal}/estado")
def device_set_estado_canal(
    canal: CanalValido = Path(..., description="Canal de dispositivo p1|p2|p3|p4"),
    body: EstadoCanalBody = None,
):
    if body is None:
        raise HTTPException(status_code=400, detail="Body requerido: {estado}")
    try:
        result = zaguan_led_client.set_estado_canal(canal, body.estado)
        actualizar_estado_canal(canal, body.estado)
        try:
            from app.services import zaguan_orchestrator as zo

            zo.set_led_state_from_console(canal, body.estado)
        except Exception:  # noqa: BLE001
            pass
        return result
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/api/zaguan/device/config/red")
def device_config_red(
    body: DeviceConfigRedBody,
    canal: CanalValido | None = Query(None),
):
    payload: dict[str, Any] = body.model_dump(exclude_none=True)
    try:
        return zaguan_led_client.config_red(payload, canal=canal)
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/api/zaguan/device/config/canal")
def device_config_canal(
    body: DeviceConfigCanalBody,
    canal: CanalValido | None = Query(None),
):
    payload: dict[str, Any] = body.model_dump(exclude_none=True)
    try:
        return zaguan_led_client.config_canal(payload, canal=canal)
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/api/zaguan/device/config/estado")
def device_config_estado(
    body: DeviceConfigEstadoBody,
    canal: CanalValido | None = Query(None),
):
    payload: dict[str, Any] = body.model_dump(exclude_none=True)
    try:
        return zaguan_led_client.config_estado(payload, canal=canal)
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/api/zaguan/device/config/flash")
def device_config_flash(
    body: DeviceConfigFlashBody,
    canal: CanalValido | None = Query(None),
):
    payload: dict[str, Any] = body.model_dump(exclude_none=True)
    try:
        return zaguan_led_client.config_flash(payload, canal=canal)
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/api/zaguan/device/ota/version")
def device_ota_version(canal: CanalValido | None = Query(None)):
    try:
        return zaguan_led_client.ota_version(canal)
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/api/zaguan/device/target")
def device_target_get():
    return zaguan_led_client.get_target()


@router.post("/api/zaguan/device/target")
def device_target_set(body: DeviceTargetBody):
    channels_payload: dict[str, Any] | None = None
    if body.channels:
        channels_payload = {
            key: entry.model_dump(exclude_none=True)
            for key, entry in body.channels.items()
        }
    try:
        return zaguan_led_client.set_target(
            host=body.host,
            port=body.port,
            timeout_s=body.timeout_s,
            channels=channels_payload,
        )
    except zaguan_led_client.ZaguanLedClientError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/zaguan/emulate/llave-echada")
def list_llave_echada_emulation():
    """Catálogo de llaves WinHose emulables (panel pulsadores)."""
    return {"llaves": list(LLAVE_ECHADA_BY_ID.values())}


@router.post("/api/zaguan/emulate/llave-echada/{llave_id}")
def emulate_llave_echada(
    llave_id: int = Path(..., ge=1, le=2),
    body: LlaveEchadaEmulateBody = ...,
):
    """
    Emula inductivo llave echada (WinHose) vía override Modbus.
    cerrar=ON, abrir=OFF; maniobra hace ON→OFF y dispara ventana 15 s en el orquestador.
    """
    meta = LLAVE_ECHADA_BY_ID.get(llave_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Llave no definida")
    board_id = int(meta["board_id"])
    channel = int(meta["channel"])
    action = body.action

    if action == "real":
        _emulate_llave_override(board_id, channel, None)
    elif action == "cerrar":
        _emulate_llave_override(board_id, channel, True)
    elif action == "abrir":
        _emulate_llave_override(board_id, channel, False)
    elif action == "maniobra":
        from app.services import zaguan_orchestrator as zo

        _emulate_llave_override(board_id, channel, True)
        _emulate_llave_override(board_id, channel, False)
        door = meta["door"]
        ok_wh, wh_reason = zo.trigger_winhose_window(door)
        if not ok_wh:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"No se activó ventana WinHose en {door}",
                    "reason": wh_reason,
                    "current_mode": zo.get_current_mode(),
                },
            )
    else:
        raise HTTPException(status_code=400, detail="Acción no válida")

    status = _poll_zaguan_after_llave_emulation()
    door = meta["door"]
    wh = (status.get("winhose_by_door") or {}).get(door) or {}
    return {
        "ok": True,
        "llave_id": llave_id,
        "action": action,
        "code": meta["code"],
        "override": None if action == "real" else (True if action == "cerrar" else False),
        "winhose_window_active": bool(wh.get("active")),
        "winhose_window_remaining_s": wh.get("remaining_s", 0.0),
        "winhose_intermittent": bool(wh.get("intermittent_scheduled")),
        "zaguan_status": status,
    }


# ══════════════════════════════════════════════════════════
#  HELPERS — llamar desde el sistema de control
# ══════════════════════════════════════════════════════════

def actualizar_estado_canal(canal: str, estado: EstadoValido):
    """
    Actualiza el estado de un canal en memoria para que
    el ESP32 lo obtenga correctamente al arrancar.

    Llamar siempre que cambie el estado de una puerta:
        actualizar_estado_canal("p1", "ocupado")
        actualizar_estado_canal("p2", "libre")
    """
    if canal in _estado_canales:
        _estado_canales[canal] = estado
        logger.debug(f"[ESP32] Estado canal {canal} → {estado}")


def get_estado_actual() -> dict:
    """Devuelve el estado actual de todos los canales."""
    return _estado_canales.copy()


async def _ejecutar_callback_pulsacion(canal: str, ts: int) -> None:
    """Ejecuta callback de pulsación sin bloquear el response HTTP."""
    try:
        if asyncio.iscoroutinefunction(_callback_pulsacion):
            await _callback_pulsacion(canal, ts)
        else:
            _callback_pulsacion(canal, ts)
    except Exception as e:
        logger.error("[ESP32] Error en callback pulsación: %s", e)
