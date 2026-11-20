"""Cliente HTTP saliente hacia una o varias placas CSIP custom1."""
from __future__ import annotations

import json
import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional
from urllib import error, request
from urllib.parse import urlparse

from app.core.config import settings
from app.csip.devices import (
    CsipDevice,
    default_device,
    get_device,
    is_multi_configured,
    list_device_ids,
)
from app.csip.schemas import ButtonEventRequest, CallStartRequest, LedControlRequest

log = logging.getLogger("csip.client")


class CsipClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def is_configured() -> bool:
    return bool(settings.csip_enabled) and is_multi_configured()


def _device_host_port(device: CsipDevice) -> tuple[str, int]:
    raw = (device.base_url or "").strip()
    if raw and "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").strip()
    if not host:
        raise CsipClientError(f"CSIP sin host en base_url ({device.id})")
    if parsed.port:
        port = int(parsed.port)
    else:
        port = 443 if (parsed.scheme or "").lower() == "https" else 80
    return host, port


def ping_device(
    device_id: str,
    *,
    timeout_s: Optional[float] = None,
) -> dict[str, Any]:
    """
    Comprueba si el Panphone/CSIP responde en TCP (puerto de base_url).
    No requiere API key; solo reachability de red.
    """
    d = get_device(device_id)
    if not d:
        return {
            "ok": False,
            "device_id": device_id,
            "error": "dispositivo no configurado",
        }
    try:
        host, port = _device_host_port(d)
    except CsipClientError as e:
        return {"ok": False, "device_id": device_id, "error": str(e)}
    timeout = max(0.3, float(timeout_s if timeout_s is not None else min(2.0, settings.csip_timeout_s)))
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return {
            "ok": True,
            "device_id": d.id,
            "host": host,
            "port": port,
            "base_url": d.base_url,
        }
    except OSError as e:
        return {
            "ok": False,
            "device_id": d.id,
            "host": host,
            "port": port,
            "base_url": d.base_url,
            "error": str(e),
        }


def ping_all_devices(*, timeout_s: Optional[float] = None) -> dict[str, Any]:
    """Ping TCP a cada placa física configurada (p1, p2, …)."""
    ids = list_device_ids()
    # Solo placas físicas: p3/p4 suelen ser alias LED de la misma IP.
    physical = [did for did in ids if did in ("p1", "p2")] or ids
    # Deduplicar por host:port
    seen_hosts: set[tuple[str, int]] = set()
    unique_ids: list[str] = []
    for did in physical:
        d = get_device(did)
        if not d:
            continue
        try:
            key = _device_host_port(d)
        except CsipClientError:
            unique_ids.append(did)
            continue
        if key in seen_hosts:
            continue
        seen_hosts.add(key)
        unique_ids.append(did)

    results: dict[str, Any] = {}
    if not unique_ids:
        return {"ok": False, "devices": {}, "online_count": 0, "total": 0}

    with ThreadPoolExecutor(max_workers=max(1, len(unique_ids))) as pool:
        futs = {
            pool.submit(ping_device, did, timeout_s=timeout_s): did for did in unique_ids
        }
        for fut in as_completed(futs):
            did = futs[fut]
            try:
                results[did] = fut.result()
            except Exception as e:  # noqa: BLE001
                results[did] = {"ok": False, "device_id": did, "error": str(e)}

    # Propagar estado a alias que comparten host (p3→p1, p4→p2).
    for did in ids:
        if did in results:
            continue
        d = get_device(did)
        if not d:
            continue
        try:
            host, port = _device_host_port(d)
        except CsipClientError:
            results[did] = {"ok": False, "device_id": did, "error": "sin host"}
            continue
        twin = next(
            (
                results[oid]
                for oid in unique_ids
                if results.get(oid)
                and results[oid].get("host") == host
                and int(results[oid].get("port") or 0) == port
            ),
            None,
        )
        if twin:
            results[did] = {**twin, "device_id": did, "alias_of": twin.get("device_id")}
        else:
            results[did] = ping_device(did, timeout_s=timeout_s)

    online = sum(1 for v in results.values() if v.get("ok"))
    return {
        "ok": online > 0,
        "devices": results,
        "online_count": online,
        "total": len(results),
        "csip_enabled": bool(settings.csip_enabled),
    }


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
    timeout_s: Optional[float] = None,
) -> dict[str, Any]:
    if not settings.csip_enabled:
        raise CsipClientError("CSIP desactivado (CSIP_ENABLED=false)")
    target = device or _resolve_device(device_id)
    url = f"{target.base_url}/{path.lstrip('/')}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(url, data=data, headers=_headers(target), method="POST")
    if timeout_s is None:
        timeout = max(0.5, float(settings.csip_timeout_s))
    else:
        timeout = max(0.5, float(timeout_s))
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
    except Exception as e:  # noqa: BLE001
        # socket.timeout en Windows a veces no es TimeoutError.
        name = type(e).__name__.lower()
        if "timeout" in name or "timed out" in str(e).lower():
            raise CsipClientError(
                f"CSIP timeout ({url}, device={target.id}, {timeout}s)"
            ) from e
        raise

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
    timeout_s: Optional[float] = None,
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    # device_id en el body no se envía a la placa
    payload.pop("device_id", None)
    target_id = device_id or body.device_id
    if not payload.get("cmd") and not (payload.get("led") and payload.get("estado")) and payload.get("brightness") is None:
        raise CsipClientError("LedControl requiere cmd, led+estado o brightness")
    log.info("CSIP led_control device=%s → %s", target_id or "(default)", payload)
    led_timeout = timeout_s
    if led_timeout is None:
        led_timeout = float(getattr(settings, "csip_led_timeout_s", None) or settings.csip_timeout_s)
    return _post(
        "led_control.php",
        payload,
        device_id=target_id,
        timeout_s=led_timeout,
    )


def button_event(
    body: ButtonEventRequest,
    *,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    log.info("CSIP button_event device=%s → %s", device_id or "(default)", payload)
    return _post("button_event.php", payload, device_id=device_id)


def audio_play(
    locucion: str,
    *,
    device_id: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> dict[str, Any]:
    """Reproduce una locución embebida en la placa (`audio_play.php`)."""
    name = (locucion or "").strip()
    if not name:
        raise CsipClientError("audio_play requiere locucion")
    payload = {"locucion": name}
    log.info("CSIP audio_play device=%s → %s", device_id or "(default)", payload)
    return _post("audio_play.php", payload, device_id=device_id, timeout_s=timeout_s)


def _led_id_for_device(device: CsipDevice) -> str:
    """Id LED en la placa (p1/p2/ALL) según config y si hay hermanos en el mismo host."""
    configured = (device.led or "ALL").strip().lower()
    if configured in ("p1", "p2", "a", "b"):
        from app.csip.devices import get_csip_devices

        siblings = [
            d for d in get_csip_devices().values() if d.base_url == device.base_url
        ]
        return configured if len(siblings) > 1 else "ALL"
    return "ALL"


def led_control_for_logical_channel(
    channel: str,
    *,
    color: str,
    brightness: Optional[int] = None,
) -> dict[str, Any]:
    """
    Empuja LED al Panphone de ``channel``.

    Prefiere ``led`` + ``estado`` (mapeo firmware):
      green→libre, orange→abriendo, red→ocupado, off→apagado.
    Así abriendo llega como estado abriendo (naranja/cometa), no como rojo.
    """
    device = get_device(channel)
    if not device:
        raise CsipClientError(f"Sin dispositivo CSIP para canal {channel}")
    led_id = _led_id_for_device(device)

    color_l = (color or "").strip().lower()
    # Si viene "efectovuelta:orange" (legacy), quedarnos con el color.
    if ":" in color_l:
        color_l = color_l.split(":")[-1]

    estado_by_color = {
        "green": "libre",
        "orange": "abriendo",
        "red": "ocupado",
        "off": "apagado",
        "libre": "libre",
        "abriendo": "abriendo",
        "ocupado": "ocupado",
        "apagado": "apagado",
    }
    estado = estado_by_color.get(color_l)
    if estado:
        # Enviar estado lógico (la placa aplica color+animación).
        body = LedControlRequest(led=led_id if led_id != "ALL" else "ALL", estado=estado, brightness=brightness)  # type: ignore[arg-type]
    else:
        body = LedControlRequest(cmd=f"{led_id}:{color_l}", brightness=brightness)
    log.info(
        "CSIP LED logical channel=%s device=%s led=%s estado/cmd=%s",
        channel,
        device.id,
        led_id,
        estado or color_l,
    )
    return led_control(body, device_id=device.id)


def led_control_winhose(
    channel: str,
    *,
    brightness: Optional[int] = None,
) -> dict[str, Any]:
    """
    Llave WinHose: el firmware aplica verde ~15 s (``cmd`` ``p1:winhouse``).

    El backend mantiene la ventana lógica; Panphone anima con su estado winhouse.
    """
    device = get_device(channel)
    if not device:
        raise CsipClientError(f"Sin dispositivo CSIP para canal {channel}")
    led_id = _led_id_for_device(device)
    body = LedControlRequest(cmd=f"{led_id}:winhouse", brightness=brightness)
    log.info(
        "CSIP LED winhouse channel=%s device=%s cmd=%s:winhouse",
        channel,
        device.id,
        led_id,
    )
    return led_control(body, device_id=device.id)
