"""Cliente HTTP backend -> dispositivo(s) ESP32 zaguán."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib import error, request

from app.core.config import BASE_DIR, settings


class ZaguanLedClientError(RuntimeError):
    pass


CHANNEL_IDS = ("p1", "p2", "p3", "p4")
# Un solo intento rápido en ping; no bloquear con timeout largo de operaciones LED.
PING_TIMEOUT_S = 0.8
_TARGET_FILE = BASE_DIR / "data" / "zaguan_device_target.json"
_runtime_target: dict[str, Any] | None = None


def _defaults() -> dict[str, Any]:
    return {
        "host": settings.zaguan_device_host,
        "port": int(settings.zaguan_device_port),
        "timeout_s": float(settings.zaguan_device_timeout_s),
        "channels": {ch: {"host": "", "port": None} for ch in CHANNEL_IDS},
    }


def _ensure_parent_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _normalize_channel_key(canal: str | int | None) -> str:
    if canal is None:
        raise ZaguanLedClientError("canal requerido")
    if isinstance(canal, int):
        if 1 <= canal <= 4:
            return f"p{canal}"
        raise ZaguanLedClientError(f"canal inválido: {canal}")
    key = str(canal).strip().lower()
    if key in CHANNEL_IDS:
        return key
    if key.isdigit() and 1 <= int(key) <= 4:
        return f"p{int(key)}"
    raise ZaguanLedClientError(f"canal inválido: {canal!r}")


def _parse_channels(raw: Any, base_port: int) -> dict[str, dict[str, Any]]:
    out = {ch: {"host": "", "port": None} for ch in CHANNEL_IDS}
    if not isinstance(raw, dict):
        return out
    for ch in CHANNEL_IDS:
        entry = raw.get(ch)
        if not isinstance(entry, dict):
            continue
        host = str(entry.get("host") or "").strip()
        port_raw = entry.get("port")
        port = int(port_raw) if port_raw not in (None, "") else None
        out[ch] = {"host": host, "port": port}
    return out


def _load_storage() -> dict[str, Any]:
    out = _defaults()
    try:
        if _TARGET_FILE.exists():
            raw = json.loads(_TARGET_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out["host"] = str(raw.get("host") or out["host"]).strip()
                out["port"] = int(raw.get("port") or out["port"])
                out["timeout_s"] = float(raw.get("timeout_s") or out["timeout_s"])
                out["channels"] = _parse_channels(raw.get("channels"), out["port"])
    except Exception:
        pass
    return out


def _uses_per_channel_ips(storage: dict[str, Any]) -> bool:
    """True si al menos un canal tiene IP propia (modo varios ESP)."""
    channels = storage.get("channels") or {}
    return any(
        bool(str((channels.get(ch) or {}).get("host") or "").strip())
        for ch in CHANNEL_IDS
    )


def _channel_is_enabled(ch: str, storage: dict[str, Any]) -> bool:
    if not _uses_per_channel_ips(storage):
        return True
    override = (storage.get("channels") or {}).get(ch) or {}
    return bool(str(override.get("host") or "").strip())


def _resolve_channel_target(canal: str, storage: dict[str, Any] | None = None) -> dict[str, Any]:
    data = storage if storage is not None else _load_storage()
    ch = _normalize_channel_key(canal)
    override = (data.get("channels") or {}).get(ch) or {}
    host_override = str(override.get("host") or "").strip()
    if _uses_per_channel_ips(data):
        if not host_override:
            raise ZaguanLedClientError(f"Canal {ch} deshabilitado (sin IP)")
        host = host_override
    else:
        host = host_override or str(data.get("host") or "").strip()
    port_raw = override.get("port")
    port = int(port_raw) if port_raw not in (None, "") else int(data.get("port") or 80)
    timeout_s = float(data.get("timeout_s") or 2.0)
    if not host:
        raise ZaguanLedClientError(f"IP no configurada para {ch} (ni global)")
    if port <= 0:
        raise ZaguanLedClientError(f"Puerto inválido para {ch}")
    return {
        "host": host,
        "port": port,
        "timeout_s": timeout_s,
        "channel": ch,
        "uses_override": bool(host_override),
        "enabled": True,
    }


def _channels_grouped_by_host(storage: dict[str, Any] | None = None) -> dict[tuple[str, int], list[str]]:
    data = storage if storage is not None else _load_storage()
    groups: dict[tuple[str, int], list[str]] = {}
    for ch in CHANNEL_IDS:
        try:
            resolved = _resolve_channel_target(ch, data)
        except ZaguanLedClientError:
            continue
        key = (resolved["host"], int(resolved["port"]))
        groups.setdefault(key, []).append(ch)
    return groups


def _enrich_target_response(storage: dict[str, Any]) -> dict[str, Any]:
    channels_out: dict[str, Any] = {}
    per_channel = _uses_per_channel_ips(storage)
    for ch in CHANNEL_IDS:
        override = (storage.get("channels") or {}).get(ch) or {}
        host_override = str(override.get("host") or "").strip()
        if per_channel and not host_override:
            channels_out[ch] = {
                "host": "",
                "port": override.get("port"),
                "resolved_host": "",
                "resolved_port": None,
                "uses_override": False,
                "enabled": False,
            }
            continue
        try:
            resolved = _resolve_channel_target(ch, storage)
        except ZaguanLedClientError:
            resolved = {
                "host": str(storage.get("host") or "").strip(),
                "port": int(storage.get("port") or 80),
            }
        channels_out[ch] = {
            "host": host_override,
            "port": override.get("port"),
            "resolved_host": resolved["host"],
            "resolved_port": resolved["port"],
            "uses_override": bool(host_override),
            "enabled": True,
        }
    return {
        "host": storage["host"],
        "port": storage["port"],
        "timeout_s": storage["timeout_s"],
        "channels": channels_out,
    }


def get_target() -> dict[str, Any]:
    global _runtime_target
    if _runtime_target is not None:
        return _enrich_target_response(_runtime_target)
    storage = _load_storage()
    _runtime_target = dict(storage)
    return _enrich_target_response(storage)


def get_channel_target(canal: str) -> dict[str, Any]:
    return _resolve_channel_target(canal, _runtime_target or _load_storage())


def set_target(
    *,
    host: str,
    port: int,
    timeout_s: float,
    channels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global _runtime_target
    payload_channels = {ch: {"host": "", "port": None} for ch in CHANNEL_IDS}
    if channels:
        for key, entry in channels.items():
            ch = _normalize_channel_key(key)
            if not isinstance(entry, dict):
                continue
            host_override = str(entry.get("host") or "").strip()
            port_raw = entry.get("port")
            port_override = int(port_raw) if port_raw not in (None, "") else None
            payload_channels[ch] = {"host": host_override, "port": port_override}

    storage = {
        "host": host.strip(),
        "port": int(port),
        "timeout_s": float(timeout_s),
        "channels": payload_channels,
    }
    if not storage["host"]:
        raise ZaguanLedClientError("host no puede estar vacío")
    if storage["port"] <= 0:
        raise ZaguanLedClientError("port debe ser mayor que 0")
    if storage["timeout_s"] <= 0:
        raise ZaguanLedClientError("timeout_s debe ser mayor que 0")

    _ensure_parent_file(_TARGET_FILE)
    _TARGET_FILE.write_text(json.dumps(storage, indent=2), encoding="utf-8")
    _runtime_target = dict(storage)
    return get_target()


def _base_url_for_channel(canal: str | None) -> str:
    if canal is None:
        storage = _runtime_target or _load_storage()
        host = str(storage.get("host") or "").strip()
        if not host:
            raise ZaguanLedClientError("ZAGUAN_DEVICE_HOST no configurado")
        port = int(storage.get("port") or 80)
    else:
        resolved = get_channel_target(canal)
        host = resolved["host"]
        port = int(resolved["port"])
    return f"http://{host}:{port}"


def _canal_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload or "canal" not in payload:
        return None
    raw = payload.get("canal")
    if raw is None:
        return None
    try:
        return _normalize_channel_key(raw)
    except ZaguanLedClientError:
        return None


def _request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    canal: str | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    url = f"{_base_url_for_channel(canal)}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if timeout_s is None:
        timeout_s = float(
            get_channel_target(canal)["timeout_s"]
            if canal
            else (get_target()["timeout_s"])
        )
    req = request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=float(timeout_s)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return {"ok": True}
            try:
                out = json.loads(raw)
                if isinstance(out, dict):
                    return out
                return {"value": out}
            except json.JSONDecodeError:
                return {"raw": raw}
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ZaguanLedClientError(f"HTTP {e.code} en {path}: {body}") from e
    except error.URLError as e:
        raise ZaguanLedClientError(f"No se pudo conectar a ESP32 ({url}): {e}") from e


def ping(canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else None
    result = _request_json("GET", "/api/ping", canal=ch, timeout_s=PING_TIMEOUT_S)
    if ch:
        result["canal"] = ch
        target = get_channel_target(ch)
        result["resolved_host"] = target["host"]
        result["resolved_port"] = target["port"]
    return result


def _ping_one_channel(ch: str, storage: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not _channel_is_enabled(ch, storage):
        return ch, {
            "ok": False,
            "pong": False,
            "disabled": True,
            "resolved_host": "",
            "resolved_port": None,
        }
    try:
        data = ping(ch)
        online = bool(data.get("pong"))
        return ch, {
            "ok": online,
            "pong": online,
            "sync": bool(data.get("sync")),
            "resolved_host": data.get("resolved_host"),
            "resolved_port": data.get("resolved_port"),
        }
    except ZaguanLedClientError as e:
        try:
            target = _resolve_channel_target(ch, storage)
            host = target["host"]
            port = target["port"]
        except ZaguanLedClientError:
            host = ""
            port = 0
        return ch, {
            "ok": False,
            "error": str(e),
            "resolved_host": host,
            "resolved_port": port,
        }


def ping_all() -> dict[str, Any]:
    storage = _runtime_target or _load_storage()
    results: dict[str, Any] = {}
    ok_count = 0
    with ThreadPoolExecutor(max_workers=len(CHANNEL_IDS)) as pool:
        futures = [pool.submit(_ping_one_channel, ch, storage) for ch in CHANNEL_IDS]
        for fut in as_completed(futures):
            ch, entry = fut.result()
            results[ch] = entry
            if entry.get("ok"):
                ok_count += 1
    return {"channels": results, "online_count": ok_count, "total": len(CHANNEL_IDS)}


def estado(canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else None
    return _request_json("GET", "/api/estado", canal=ch)


def estado_all() -> dict[str, Any]:
    storage = _runtime_target or _load_storage()
    groups = _channels_grouped_by_host(storage)
    merged: dict[int, dict[str, Any]] = {}
    sync = True
    for (_host, _port), ch_list in groups.items():
        try:
            if len(ch_list) == len(CHANNEL_IDS):
                data = _request_json("GET", "/api/estado", canal=ch_list[0])
            else:
                data = {"canales": [], "sync": True}
                for ch in ch_list:
                    one = estado(ch)
                    sync = sync and bool(one.get("sync", False))
                    for item in one.get("canales") or []:
                        if isinstance(item, dict):
                            num = int(item.get("canal") or ch[1])
                            merged[num] = item
                continue
            sync = sync and bool(data.get("sync", False))
            for item in data.get("canales") or []:
                if isinstance(item, dict) and item.get("canal") is not None:
                    merged[int(item["canal"])] = item
        except ZaguanLedClientError:
            sync = False
    return {"canales": [merged[k] for k in sorted(merged)], "sync": sync}


def config_get(canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else None
    data = _request_json("GET", "/api/config", canal=ch)
    if ch:
        data["canal"] = ch
    return data


def set_estado_canal(canal: str, estado_value: str) -> dict[str, Any]:
    ch = _normalize_channel_key(canal)
    return _request_json("POST", f"/api/{ch}/estado", {"estado": estado_value}, canal=ch)


def config_red(payload: dict[str, Any], canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else _canal_from_payload(payload)
    return _request_json("POST", "/api/config/red", payload, canal=ch)


def config_canal(payload: dict[str, Any], canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else _canal_from_payload(payload)
    return _request_json("POST", "/api/config/canal", payload, canal=ch)


def config_estado(payload: dict[str, Any], canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else _canal_from_payload(payload)
    return _request_json("POST", "/api/config/estado", payload, canal=ch)


def config_flash(payload: dict[str, Any], canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else None
    return _request_json("POST", "/api/config/flash", payload, canal=ch)


def ota_version(canal: str | None = None) -> dict[str, Any]:
    ch = _normalize_channel_key(canal) if canal else None
    data = _request_json("GET", "/api/ota/version", canal=ch)
    if ch:
        data["canal"] = ch
    return data
