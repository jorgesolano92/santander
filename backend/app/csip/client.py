"""Cliente HTTP saliente hacia la API custom1 de la placa CSIP."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib import error, request

from app.core.config import settings
from app.csip.schemas import ButtonEventRequest, CallStartRequest, LedControlRequest

log = logging.getLogger("csip.client")


class CsipClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def is_configured() -> bool:
    return bool((settings.csip_base_url or "").strip()) and bool(settings.csip_enabled)


def _base_url() -> str:
    base = (settings.csip_base_url or "").strip().rstrip("/")
    if not base:
        raise CsipClientError("CSIP_BASE_URL no configurada")
    return base


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    token = (settings.csip_api_token or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
        h["X-API-Key"] = token
    return h


def _post(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not settings.csip_enabled:
        raise CsipClientError("CSIP desactivado (CSIP_ENABLED=false)")
    url = f"{_base_url()}/{path.lstrip('/')}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(url, data=data, headers=_headers(), method="POST")
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
            f"CSIP HTTP {e.code} en {path}: {raw[:300]}",
            status_code=int(e.code),
            body=parsed,
        ) from e
    except error.URLError as e:
        raise CsipClientError(f"CSIP no alcanzable ({url}): {e.reason}") from e

    if not raw.strip():
        return {"status": "ok", "http_code": status}
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "ok", "http_code": status, "raw": raw}
    if isinstance(out, dict):
        out.setdefault("http_code", status)
        return out
    return {"status": "ok", "http_code": status, "data": out}


def call_start(body: CallStartRequest) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    log.info("CSIP call_start → %s", payload)
    return _post("call_start.php", payload)


def led_control(body: LedControlRequest) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    if not payload.get("cmd") and not (payload.get("led") and payload.get("estado")) and payload.get("brightness") is None:
        raise CsipClientError("LedControl requiere cmd, led+estado o brightness")
    log.info("CSIP led_control → %s", payload)
    return _post("led_control.php", payload)


def button_event(body: ButtonEventRequest) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    log.info("CSIP button_event → %s", payload)
    return _post("button_event.php", payload)
