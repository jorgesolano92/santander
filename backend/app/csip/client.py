"""Cliente HTTP saliente hacia una o varias placas CSIP custom1."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib import error, request

from app.core.config import settings
from app.csip.devices import CsipDevice, default_device, get_device, is_multi_configured
from app.csip.schemas import ButtonEventRequest, CallStartRequest, LedControlRequest

log = logging.getLogger("csip.client")


class CsipClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def is_configured() -> bool:
    return bool(settings.csip_enabled) and is_multi_configured()


def _resolve_device(device_id: Optional[str] = None) -> CsipDevice:
    if device_id:
        d = get_device(device_id)
        if not d:
            raise CsipClientError(f"Dispositivo CSIP desconocido: {device_id}")
        return d
    d = default_device()
    if not d:
        raise CsipClientError("Ningún dispositivo CSIP configurado (CSIP_DEVICES o CSIP_BASE_URL)")
    return d


def _headers(device: CsipDevice) -> dict[str, str]:
    h = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    token = (device.token or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
        h["X-API-Key"] = token
    return h


def _post(
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    device_id: Optional[str] = None,
    device: Optional[CsipDevice] = None,
) -> dict[str, Any]:
    if not settings.csip_enabled:
        raise CsipClientError("CSIP desactivado (CSIP_ENABLED=false)")
    target = device or _resolve_device(device_id)
    url = f"{target.base_url}/{path.lstrip('/')}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(url, data=data, headers=_headers(target), method="POST")
    timeout = max(0.5, float(settings.csip_timeout_s))
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200) or 200
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        parsed: Any
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        raise CsipClientError(
            f"CSIP HTTP {e.code} en {path} ({target.id}): {raw[:300]}",
            status_code=int(e.code),
            body=parsed,
        ) from e
    except error.URLError as e:
        raise CsipClientError(
            f"CSIP no alcanzable ({url}, device={target.id}): {e.reason}"
        ) from e

    if not raw.strip():
        return {"status": "ok", "http_code": status, "device_id": target.id}
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "ok", "http_code": status, "raw": raw, "device_id": target.id}
    if isinstance(out, dict):
        out.setdefault("http_code", status)
        out.setdefault("device_id", target.id)
        return out
    return {"status": "ok", "http_code": status, "data": out, "device_id": target.id}


def call_start(
    body: CallStartRequest,
    *,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    payload.pop("device_id", None)
    target_id = device_id or body.device_id
    log.info("CSIP call_start device=%s → %s", target_id or "(default)", payload)
    return _post("call_start.php", payload, device_id=target_id)


def led_control(
    body: LedControlRequest,
    *,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    # device_id en el body no se envía a la placa
    payload.pop("device_id", None)
    target_id = device_id or body.device_id
    if not payload.get("cmd") and not (payload.get("led") and payload.get("estado")) and payload.get("brightness") is None:
        raise CsipClientError("LedControl requiere cmd, led+estado o brightness")
    log.info("CSIP led_control device=%s → %s", target_id or "(default)", payload)
    return _post("led_control.php", payload, device_id=target_id)


def button_event(
    body: ButtonEventRequest,
    *,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    log.info("CSIP button_event device=%s → %s", device_id or "(default)", payload)
    return _post("button_event.php", payload, device_id=device_id)


def led_control_for_logical_channel(
    channel: str,
    *,
    color: str,
    brightness: Optional[int] = None,
) -> dict[str, Any]:
    """
    Empuja un color LED al Panphone mapeado para ``channel`` (p1, p2, …).
    Usa el ``led`` físico configurado en CSIP_DEVICES (p. ej. siempre p1 en placas de un botón).
    """
    device = get_device(channel)
    if not device:
        raise CsipClientError(f"Sin dispositivo CSIP para canal {channel}")
    led_id = (device.led or "p1").strip().lower()
    cmd = f"{led_id}:{color}"
    body = LedControlRequest(cmd=cmd, brightness=brightness)
    return led_control(body, device_id=device.id)
