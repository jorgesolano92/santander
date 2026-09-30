"""Registro de placas Panphone / CSIP (N dispositivos).

Configuración preferida (JSON en env ``CSIP_DEVICES``)::

    {
      "p1": {
        "base_url": "http://192.168.1.70:8090/api/custom1",
        "token": "api-key-placa-1",
        "led": "p1"
      },
      "p2": {
        "base_url": "http://192.168.1.80:8090/api/custom1",
        "token": "api-key-placa-2",
        "led": "p1"
      }
    }

- La clave (``p1``, ``p2``, ``p3``…) es el canal lógico (notify + orquestador).
- ``led`` es el id LED en esa placa física (suele ser ``p1`` si solo tiene un botón).
- ``token`` opcional; si falta, se usa ``CSIP_API_TOKEN``.

Compatibilidad: si ``CSIP_DEVICES`` está vacío y hay ``CSIP_BASE_URL``, se sintetiza
un mapa ``p1``+``p2`` apuntando al mismo host (canales LED p1/p2 en una sola placa).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.core.config import settings

log = logging.getLogger("csip.devices")

_DEVICE_ID_RE = re.compile(r"^p\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class CsipDevice:
    """Una placa Panphone alcanzable por HTTP."""

    id: str
    base_url: str
    token: Optional[str] = None
    """Id LED en la placa (p1/p2/ALL). Por defecto = id lógico."""
    led: str = "p1"


_cached_raw: Optional[str] = None
_cached_map: dict[str, CsipDevice] = {}


def _normalize_base_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _parse_devices_json(raw: str) -> dict[str, CsipDevice]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("CSIP_DEVICES debe ser un objeto JSON {id: {...}}")
    out: dict[str, CsipDevice] = {}
    default_token = (settings.csip_api_token or "").strip() or None
    for key, val in data.items():
        did = str(key).strip().lower()
        if not _DEVICE_ID_RE.match(did):
            log.warning("CSIP_DEVICES: id %r ignorado (usar p1, p2, p3…)", key)
            continue
        if isinstance(val, str):
            base = _normalize_base_url(val)
            token = default_token
            led = "p1"
        elif isinstance(val, dict):
            base = _normalize_base_url(
                str(val.get("base_url") or val.get("url") or val.get("host") or "")
            )
            tok = val.get("token") or val.get("api_token") or val.get("api_key")
            token = (str(tok).strip() if tok else None) or default_token
            led_raw = val.get("led") or val.get("led_id") or "p1"
            led = str(led_raw).strip().lower() or "p1"
            # Si dieron host sin path, añadir /api/custom1
            if base and "://" in base and "/api/" not in base:
                # host:puerto o http://host:8090
                if base.count("/") <= 2:
                    host = base
                    if not host.startswith("http"):
                        host = f"http://{host}"
                    base = f"{host.rstrip('/')}/api/custom1"
        else:
            log.warning("CSIP_DEVICES[%s]: valor inválido", did)
            continue
        if not base:
            log.warning("CSIP_DEVICES[%s]: sin base_url", did)
            continue
        out[did] = CsipDevice(id=did, base_url=base, token=token, led=led)
    return out


def _legacy_single_host_map() -> dict[str, CsipDevice]:
    base = _normalize_base_url(settings.csip_base_url or "")
    if not base:
        return {}
    token = (settings.csip_api_token or "").strip() or None
    # Misma placa, dos canales LED (comportamiento histórico).
    return {
        "p1": CsipDevice(id="p1", base_url=base, token=token, led="p1"),
        "p2": CsipDevice(id="p2", base_url=base, token=token, led="p2"),
    }


def get_csip_devices() -> dict[str, CsipDevice]:
    """Mapa id → dispositivo (cache invalidada si cambia el env JSON)."""
    global _cached_raw, _cached_map
    raw = (getattr(settings, "csip_devices", None) or "").strip()
    if raw == (_cached_raw or "") and _cached_map:
        return dict(_cached_map)
    if raw:
        try:
            parsed = _parse_devices_json(raw)
        except Exception as e:  # noqa: BLE001
            log.error("CSIP_DEVICES JSON inválido: %s", e)
            parsed = {}
        _cached_raw = raw
        _cached_map = parsed
        return dict(parsed)
    legacy = _legacy_single_host_map()
    _cached_raw = ""
    _cached_map = legacy
    return dict(legacy)


def get_device(device_id: str) -> Optional[CsipDevice]:
    did = (device_id or "").strip().lower()
    return get_csip_devices().get(did)


def list_device_ids() -> list[str]:
    return sorted(get_csip_devices().keys(), key=lambda x: (len(x), x))


def is_multi_configured() -> bool:
    return bool(get_csip_devices())


def default_device() -> Optional[CsipDevice]:
    """Primer dispositivo (para proxy sin device_id). Preferencia p1."""
    devices = get_csip_devices()
    if not devices:
        return None
    if "p1" in devices:
        return devices["p1"]
    return devices[list_device_ids()[0]]


def devices_public_status() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for did in list_device_ids():
        d = get_csip_devices()[did]
        rows.append(
            {
                "id": d.id,
                "base_url": d.base_url,
                "led": d.led,
                "token_configured": bool(d.token),
            }
        )
    return rows
