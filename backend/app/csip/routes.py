"""
Rutas CSIP custom1 — módulo aparte, mismo FastAPI.

Webhooks (placa → nosotros), públicos salvo CSIP_WEBHOOK_TOKEN:
  POST /api/csip/notify/p1
  POST /api/csip/notify/p2
  POST /api/csip/notify   (body.button_id / canal)

Proxy hacia la placa (panel JWT):
  POST /api/csip/device/call_start
  POST /api/csip/device/led_control
  POST /api/csip/device/button_event
  GET  /api/csip/status
  GET  /api/csip/health
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Path, Request, status

from app.core.config import settings
from app.csip import client as csip_client
from app.csip import state as csip_state
from app.csip.schemas import (
    ButtonEventRequest,
    CallStartRequest,
    CsipNotifyAck,
    CsipStatusResponse,
    LedControlRequest,
    NotifyCanal,
)

log = logging.getLogger("csip.routes")

router = APIRouter(prefix="/csip", tags=["CSIP Panphone"])


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


async def _forward_zaguan(canal: NotifyCanal, body: dict[str, Any]) -> bool:
    if not settings.csip_forward_pulsacion_to_zaguan:
        return False
    ts_raw = body.get("ts") or body.get("timestamp") or int(time.time() * 1000)
    try:
        ts = int(ts_raw)
    except (TypeError, ValueError):
        ts = int(time.time() * 1000)
    try:
        from app.services import zaguan_orchestrator

        await zaguan_orchestrator.handle_pulsacion(canal, ts)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("CSIP notify: fallo al reenviar a zaguán (%s): %s", canal, e)
        return False


@router.get("/health", summary="Salud del módulo CSIP")
def csip_health() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "csip",
        "enabled": bool(settings.csip_enabled),
        "base_url_configured": bool((settings.csip_base_url or "").strip()),
    }


@router.get("/status", response_model=CsipStatusResponse, summary="Estado integración CSIP")
def csip_status() -> CsipStatusResponse:
    base = _mask_url(settings.csip_base_url)
    return CsipStatusResponse(
        enabled=bool(settings.csip_enabled),
        base_url_configured=bool(base),
        base_url=base,
        api_token_configured=bool((settings.csip_api_token or "").strip()),
        webhook_token_required=bool((settings.csip_webhook_token or "").strip()),
        forward_pulsacion_to_zaguan=bool(settings.csip_forward_pulsacion_to_zaguan),
        timeout_s=float(settings.csip_timeout_s),
        recent_notifications=csip_state.list_recent(20),
    )


@router.post(
    "/notify/{canal}",
    response_model=CsipNotifyAck,
    summary="Webhook placa → app (notification_url/p1|p2)",
)
async def csip_notify_canal(
    request: Request,
    canal: NotifyCanal = Path(..., description="p1 o p2"),
) -> CsipNotifyAck:
    _require_webhook_auth(request)
    body = await _read_body_dict(request)
    body.setdefault("button_id", canal)
    body.setdefault("canal", canal)
    log.info("CSIP notify %s ← %s", canal, body)
    forwarded = await _forward_zaguan(canal, body)
    entry = csip_state.record_notification(canal, body, forwarded=forwarded)
    return CsipNotifyAck(
        ok=True,
        canal=canal,
        forwarded_to_zaguan=forwarded,
        received_at=entry["received_at"],
        body=body,
    )


@router.post("/notify", response_model=CsipNotifyAck, summary="Webhook genérico (button_id)")
async def csip_notify(request: Request) -> CsipNotifyAck:
    _require_webhook_auth(request)
    body = await _read_body_dict(request)
    raw_id = str(body.get("button_id") or body.get("canal") or body.get("led") or "").strip().lower()
    if raw_id in ("push", "5", "1"):
        raw_id = "p1"
    if raw_id not in ("p1", "p2"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Indica button_id o canal: p1 | p2",
        )
    canal: NotifyCanal = raw_id  # type: ignore[assignment]
    body.setdefault("button_id", canal)
    body.setdefault("canal", canal)
    log.info("CSIP notify %s ← %s", canal, body)
    forwarded = await _forward_zaguan(canal, body)
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


@router.post("/device/call_start", summary="Proxy → placa call_start.php")
def device_call_start(body: CallStartRequest) -> dict[str, Any]:
    try:
        return csip_client.call_start(body)
    except csip_client.CsipClientError as e:
        raise _device_error(e) from e


@router.post("/device/led_control", summary="Proxy → placa led_control.php")
def device_led_control(body: LedControlRequest) -> dict[str, Any]:
    try:
        return csip_client.led_control(body)
    except csip_client.CsipClientError as e:
        raise _device_error(e) from e


@router.post("/device/button_event", summary="Proxy → placa button_event.php")
def device_button_event(body: ButtonEventRequest) -> dict[str, Any]:
    try:
        return csip_client.button_event(body)
    except csip_client.CsipClientError as e:
        raise _device_error(e) from e
