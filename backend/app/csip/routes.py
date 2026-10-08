"""
Rutas CSIP custom1 — módulo aparte, mismo FastAPI.

Webhooks (placa → nosotros), públicos salvo CSIP_WEBHOOK_TOKEN:
  POST /api/csip/notify/p1
  POST /api/csip/notify/p2
  POST /api/csip/notify/push   (alias exterior → p1 local)
  POST /api/csip/notify/p3   (N canales: p1…pN)
  POST /api/csip/notify      (body.button_id / canal)

Proxy hacia la(s) placa(s) (panel JWT):
  POST /api/csip/device/call_start
  POST /api/csip/device/led_control
  POST /api/csip/device/button_event
  GET  /api/csip/status
  GET  /api/csip/health
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Path, Request, status

from app.core.config import settings
from app.csip import client as csip_client
from app.csip import state as csip_state
from app.csip.devices import (
    default_device,
    devices_public_status,
    find_plate_device_id_by_host,
    get_device,
    list_device_ids,
    map_plate_button_to_logical,
)
from app.csip.schemas import (
    ButtonEventRequest,
    CallStartRequest,
    CsipDeviceStatus,
    CsipNotifyAck,
    CsipStatusResponse,
    LedControlRequest,
)

log = logging.getLogger("csip.routes")

router = APIRouter(prefix="/csip", tags=["CSIP Panphone"])

_CANAL_RE = re.compile(r"^p\d+$", re.IGNORECASE)
_ZAGUAN_PULSADORES = frozenset({"p1", "p2", "p3", "p4"})


def _normalize_canal_id(raw: Any) -> Optional[str]:
    """
    Acepta p1/p2, enteros 1/2 (como envía Panphone en el body) y aliases.
    """
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in ("push", "5"):
        return "p1"
    if s.isdigit():
        return f"p{int(s)}"
    if _CANAL_RE.match(s):
        return s
    m = re.match(r"^p(\d+)$", s)
    if m:
        return f"p{int(m.group(1))}"
    return None


def _parse_canal_or_400(raw: str) -> str:
    canal = _normalize_canal_id(raw)
    if not canal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Indica button_id o canal: p1, p2, p3… (o 1, 2, 3…)",
        )
    return canal


def _mask_url(url: str) -> Optional[str]:
    u = (url or "").strip()
    return u or None


def _extract_webhook_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    key = (request.headers.get("X-API-Key") or "").strip()
    return key or None


def _require_webhook_auth(request: Request) -> None:
    expected = (settings.csip_webhook_token or "").strip()
    if not expected:
        return
    got = _extract_webhook_token(request)
    if got != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token CSIP webhook ausente o incorrecto",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _read_body_dict(request: Request) -> dict[str, Any]:
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            data = None
        return data if isinstance(data, dict) else {}
    if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
        form = await request.form()
        return {str(k): form.get(k) for k in form.keys()}
    raw = (await request.body()).decode("utf-8", errors="replace").strip()
    if not raw:
        return {}
    try:
        import json

        data = json.loads(raw)
        return data if isinstance(data, dict) else {"raw": raw}
    except Exception:  # noqa: BLE001
        return {"raw": raw}


def _client_host(request: Request) -> str:
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return ""


def _remap_notify_canal(request: Request, plate_button: str) -> tuple[str, Optional[str]]:
    """
    Cada Panphone añade /p1|/p2 según su botón LOCAL (no existen p3/p4 en placa).
    Remapea por IP a canal lógico (LED); la puerta la decide el orquestador:
      .80 = puerta P1: local p1→p1 (ext), local p2→p3 (int)  → ambos abren P1
      .70 = puerta P2: local p1→p2 (ext), local p2→p4 (int)  → ambos abren P2
    """
    plate_btn = _parse_canal_or_400(plate_button)
    host = _client_host(request)
    plate_id = find_plate_device_id_by_host(host)
    logical = map_plate_button_to_logical(
        plate_device_id=plate_id,
        plate_button=plate_btn,
    )
    if plate_id and logical != plate_btn:
        log.info(
            "CSIP notify remap %s → %s (placa=%s host=%s)",
            plate_btn,
            logical,
            plate_id,
            host or "?",
        )
    elif not plate_id:
        if settings.device_webhook_known_hosts_only:
            log.warning("CSIP notify rechazado: IP %s no es un Panphone configurado", host or "?")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origen no autorizado: la IP no corresponde a ningún Panphone configurado",
            )
        log.warning(
            "CSIP notify sin placa por IP (%s); uso botón local %s sin remap",
            host or "?",
            plate_btn,
        )
    return logical, plate_id


def _pulsacion_ts(body: dict[str, Any]) -> int:
    ts_raw = body.get("ts") or body.get("timestamp") or int(time.time() * 1000)
    try:
        return int(ts_raw)
    except (TypeError, ValueError):
        return int(time.time() * 1000)


async def _forward_zaguan(canal: str, body: dict[str, Any]) -> bool:
    """Ejecuta la pulsación (bloqueante: incluye pulso Modbus ~2s)."""
    if not settings.csip_forward_pulsacion_to_zaguan:
        return False
    if canal not in _ZAGUAN_PULSADORES:
        log.info(
            "CSIP notify %s: sin mapeo zaguán (solo p1–p4 se reenvían); se registra igual",
            canal,
        )
        return False
    ts = _pulsacion_ts(body)
    try:
        from app.services import zaguan_orchestrator

        await zaguan_orchestrator.handle_pulsacion(canal, ts)  # type: ignore[arg-type]
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("CSIP notify: fallo al reenviar a zaguán (%s): %s", canal, e)
        return False


def _queue_forward_zaguan(canal: str, body: dict[str, Any]) -> bool:
    """
    ACK rápido a la placa: la apertura Modbus no debe bloquear notification_url.

    Si el webhook espera el pulso (~2s), el Panphone marca http_error/http_code=0
    y el botón exterior (videoportero + SIP) parece no hacer nada.
    """
    if not settings.csip_forward_pulsacion_to_zaguan:
        return False
    if canal not in _ZAGUAN_PULSADORES:
        log.info(
            "CSIP notify %s: sin mapeo zaguán (solo p1–p4 se reenvían); se registra igual",
            canal,
        )
        return False

    async def _run() -> None:
        ok = await _forward_zaguan(canal, body)
        if not ok:
            log.warning("CSIP notify background: pulsación %s no reenviada", canal)

    try:
        asyncio.get_running_loop().create_task(
            _run(),
            name=f"csip-forward-{canal}",
        )
    except TypeError:
        # Python <3.11: create_task sin name=
        asyncio.get_running_loop().create_task(_run())
    return True


@router.get("/health", summary="Salud del módulo CSIP")
def csip_health() -> dict[str, Any]:
    ids = list_device_ids()
    return {
        "ok": True,
        "module": "csip",
        "enabled": bool(settings.csip_enabled),
        "base_url_configured": bool((settings.csip_base_url or "").strip()) or bool(ids),
        "device_count": len(ids),
        "device_ids": ids,
    }


@router.get("/status", response_model=CsipStatusResponse, summary="Estado integración CSIP")
def csip_status() -> CsipStatusResponse:
    devices = [CsipDeviceStatus(**row) for row in devices_public_status()]
    legacy = _mask_url(settings.csip_base_url)
    primary = devices[0].base_url if devices else legacy
    return CsipStatusResponse(
        enabled=bool(settings.csip_enabled),
        base_url_configured=bool(primary),
        base_url=primary,
        api_token_configured=bool((settings.csip_api_token or "").strip())
        or any(d.token_configured for d in devices),
        webhook_token_required=bool((settings.csip_webhook_token or "").strip()),
        forward_pulsacion_to_zaguan=bool(settings.csip_forward_pulsacion_to_zaguan),
        timeout_s=float(settings.csip_timeout_s),
        devices=devices,
        recent_notifications=csip_state.list_recent(20),
    )


@router.post(
    "/notify/{canal}",
    response_model=CsipNotifyAck,
    summary="Webhook placa → app (notification_url/p1|p2|push…)",
)
async def csip_notify_canal(
    request: Request,
    canal: str = Path(
        ...,
        description="Botón local placa p1|p2|push|5 (se remapea por IP)",
        pattern=r"^(?:p\d+|push|5)$",
    ),
) -> CsipNotifyAck:
    _require_webhook_auth(request)
    plate_button = _parse_canal_or_400(canal)
    body = await _read_body_dict(request)
    canal_n, plate_id = _remap_notify_canal(request, plate_button)
    body["plate_button"] = plate_button
    body["plate_device_id"] = plate_id
    body["button_id"] = canal_n
    body["canal"] = canal_n
    log.info(
        "CSIP notify %s ← host=%s plate=%s body=%s",
        canal_n,
        _client_host(request) or "?",
        plate_id or "?",
        body,
    )
    # Responder ya: el pulso Modbus no debe retrasar el ACK a la placa.
    forwarded = _queue_forward_zaguan(canal_n, body)
    entry = csip_state.record_notification(canal_n, body, forwarded=forwarded)
    return CsipNotifyAck(
        ok=True,
        canal=canal_n,
        forwarded_to_zaguan=forwarded,
        received_at=entry["received_at"],
        body=body,
    )


@router.post("/notify", response_model=CsipNotifyAck, summary="Webhook genérico (button_id)")
async def csip_notify(request: Request) -> CsipNotifyAck:
    """
    URL base que debe ir en notification_url de la placa:
      http://<backend>:8000/api/csip/notify
    La placa añade sola /p1 o /p2 según el botón configurado en el Panphone.
    Si llega aquí sin sufijo, se usa body.canal / button_id (acepta 1/2 o p1/p2).
    """
    _require_webhook_auth(request)
    body = await _read_body_dict(request)
    plate_button = _normalize_canal_id(
        body.get("button_id") or body.get("canal") or body.get("led")
    )
    if not plate_button:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Indica button_id o canal: p1|p2 (o 1/2, push, 5). "
            "Mejor: notification_url sin sufijo y deja que la placa añada /p1|/p2.",
        )
    canal, plate_id = _remap_notify_canal(request, plate_button)
    body["plate_button"] = plate_button
    body["plate_device_id"] = plate_id
    body["button_id"] = canal
    body["canal"] = canal
    log.info(
        "CSIP notify %s ← host=%s plate=%s body=%s",
        canal,
        _client_host(request) or "?",
        plate_id or "?",
        body,
    )
    forwarded = _queue_forward_zaguan(canal, body)
    entry = csip_state.record_notification(canal, body, forwarded=forwarded)
    return CsipNotifyAck(
        ok=True,
        canal=canal,
        forwarded_to_zaguan=forwarded,
        received_at=entry["received_at"],
        body=body,
    )


def _device_error(exc: csip_client.CsipClientError) -> HTTPException:
    code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    if code == 401:
        http_status = status.HTTP_401_UNAUTHORIZED
    elif code == 403:
        http_status = status.HTTP_403_FORBIDDEN
    elif code == 400:
        http_status = status.HTTP_400_BAD_REQUEST
    elif 400 <= code < 600:
        http_status = status.HTTP_502_BAD_GATEWAY
    else:
        http_status = status.HTTP_502_BAD_GATEWAY
    return HTTPException(
        status_code=http_status,
        detail={"error": str(exc), "remote_status": exc.status_code, "remote_body": exc.body},
    )


def _resolve_proxy_device_id(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        if not get_device(explicit):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"device_id desconocido: {explicit}. Configurados: {list_device_ids()}",
            )
        return explicit.strip().lower()
    d = default_device()
    return d.id if d else None


@router.post("/device/call_start", summary="Proxy → placa call_start.php")
def device_call_start(body: CallStartRequest) -> dict[str, Any]:
    try:
        device_id = _resolve_proxy_device_id(body.device_id)
        payload = body.model_copy(update={"device_id": None})
        return csip_client.call_start(payload, device_id=device_id)
    except csip_client.CsipClientError as e:
        raise _device_error(e) from e


@router.post("/device/led_control", summary="Proxy → placa led_control.php")
def device_led_control(body: LedControlRequest) -> dict[str, Any]:
    try:
        device_id = _resolve_proxy_device_id(body.device_id)
        return csip_client.led_control(body, device_id=device_id)
    except csip_client.CsipClientError as e:
        raise _device_error(e) from e


@router.post("/device/button_event", summary="Proxy → placa button_event.php")
def device_button_event(body: ButtonEventRequest, device_id: Optional[str] = None) -> dict[str, Any]:
    try:
        resolved = _resolve_proxy_device_id(device_id)
        return csip_client.button_event(body, device_id=resolved)
    except csip_client.CsipClientError as e:
        raise _device_error(e) from e
