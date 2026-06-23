"""Llamadas al backend de cada sucursal (solo desde servidor COCE)."""
from __future__ import annotations

import socket
from typing import Any, Optional

import httpx

from app.services.host_utils import normalize_host


def _default_location() -> dict[str, Any]:
    return {
        "address": "",
        "latitude": None,
        "longitude": None,
        "captured_at": None,
    }


def _default_branch_map_info() -> dict[str, Any]:
    return {
        **_default_location(),
        "current_mode": None,
        "mode_label": None,
        "mode_color": None,
        "opening_hours": None,
        "schedules_enabled": None,
    }


def _branch_map_info_from_response(data: Any) -> dict[str, Any]:
    base = _default_branch_map_info()
    if not isinstance(data, dict):
        return base
    address = data.get("address")
    if isinstance(address, str):
        base["address"] = address.strip()
    for key in ("latitude", "longitude"):
        val = data.get(key)
        if val is None or val == "":
            continue
        try:
            base[key] = float(val)
        except (TypeError, ValueError):
            pass
    captured = data.get("captured_at")
    if isinstance(captured, str) and captured.strip():
        base["captured_at"] = captured.strip()
    mode = data.get("current_mode")
    if isinstance(mode, str) and mode.strip():
        base["current_mode"] = mode.strip()
    label = data.get("mode_label")
    if isinstance(label, str) and label.strip():
        base["mode_label"] = label.strip()
    color = data.get("mode_color")
    if isinstance(color, str) and color.strip():
        base["mode_color"] = color.strip()
    hours = data.get("opening_hours")
    if isinstance(hours, str) and hours.strip():
        base["opening_hours"] = hours.strip()
    if "schedules_enabled" in data:
        base["schedules_enabled"] = bool(data.get("schedules_enabled"))
    return base


def branch_base_url(branch: dict[str, Any]) -> str:
    host = normalize_host(str(branch["host"]))
    proto = "https" if branch.get("useHttps") else "http"
    return f"{proto}://{host}:{int(branch['port'])}"


def _connection_error_message(base: str, err: Exception) -> str:
    host = base.split("://", 1)[-1].rsplit(":", 1)[0]
    msg = str(err).lower()
    if "getaddrinfo" in msg or "11001" in msg or "name or service not known" in msg:
        return (
            f"No se pudo resolver el host «{host}». "
            "Revisa la IP en la ficha de la sucursal (ej. 192.168.1.155, sin puntos de más). "
            "El servidor COCE debe poder alcanzar esa IP en red; «localhost» solo sirve si el backend "
            "de sucursal corre en el mismo PC que coce-api."
        )
    return (
        f"No se pudo conectar a {base}. "
        "Comprueba que el backend de la oficina esté en marcha, el puerto, el firewall y la VPN."
    )


async def _read_error(res: httpx.Response) -> str:
    try:
        data = res.json()
        if isinstance(data, dict):
            d = data.get("detail")
            if isinstance(d, str):
                return d
            if d is not None:
                return str(d)
    except Exception:
        pass
    return res.text or res.reason_phrase


async def tablet_login(base: str, user: str, password: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{base}/api/v1/auth/token",
                data={"username": user, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, socket.gaierror, OSError) as e:
        raise RuntimeError(_connection_error_message(base, e)) from e
    if res.status_code >= 400:
        raise RuntimeError(await _read_error(res))
    data = res.json()
    tok = data.get("access_token")
    if not tok:
        raise RuntimeError("Respuesta sin access_token (tablet)")
    return str(tok)


async def panel_login(base: str, user: str, password: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{base}/api/auth/login",
                json={"username": user, "password": password},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, socket.gaierror, OSError) as e:
        raise RuntimeError(_connection_error_message(base, e)) from e
    if res.status_code >= 400:
        raise RuntimeError(await _read_error(res))
    data = res.json()
    tok = data.get("access_token")
    if not tok:
        raise RuntimeError("Respuesta sin access_token (panel)")
    return str(tok)


async def fetch_branch_location(branch: dict[str, Any]) -> dict[str, Any]:
    """GET /api/v1/branch/location en sucursal (rápido, solo BD local)."""
    base = branch_base_url(branch)
    tablet_tok = await tablet_login(
        base, branch["usuarioTablet"], branch["passwordTablet"]
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{base}/api/v1/branch/location",
                headers={"Authorization": f"Bearer {tablet_tok}"},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, socket.gaierror, OSError) as e:
        raise RuntimeError(_connection_error_message(base, e)) from e
    if res.status_code >= 400:
        raise RuntimeError(await _read_error(res))
    return _branch_map_info_from_response(res.json())


async def fetch_branch_snapshot(
    branch: dict[str, Any],
    *,
    refresh_hardware: bool = False,
) -> dict[str, Any]:
    base = branch_base_url(branch)
    tablet_tok = await tablet_login(
        base, branch["usuarioTablet"], branch["passwordTablet"]
    )
    async with httpx.AsyncClient(timeout=45.0) as client:
        modes_res, mode_res = await client.get(
            f"{base}/api/v1/modes",
            headers={"Authorization": f"Bearer {tablet_tok}"},
        ), await client.get(
            f"{base}/api/v1/get_mode",
            headers={"Authorization": f"Bearer {tablet_tok}"},
        )
        if modes_res.status_code >= 400:
            raise RuntimeError(await _read_error(modes_res))
        if mode_res.status_code >= 400:
            raise RuntimeError(await _read_error(mode_res))
        modes_data = modes_res.json()
        mode_data = mode_res.json()

    boards: dict[str, Any] = {}
    modules_config: list[Any] = []
    panel_timestamp: Optional[str] = None
    panel_ok = False
    panel_error: Optional[str] = None
    location = _default_branch_map_info()
    try:
        location = await fetch_branch_location(branch)
    except Exception:
        pass

    pu = (branch.get("usuarioPanel") or "").strip()
    pp = branch.get("passwordPanel") or ""
    if pu and pp:
        try:
            panel_tok = await panel_login(base, pu, pp)
            async with httpx.AsyncClient(timeout=45.0) as client:
                st = await client.get(
                    f"{base}/api/panel/status",
                    headers={"Authorization": f"Bearer {panel_tok}"},
                    params={"refresh_hardware": str(refresh_hardware).lower()},
                )
            if st.status_code >= 400:
                panel_error = await _read_error(st)
            else:
                status = st.json()
                boards = status.get("boards") or {}
                modules_config = status.get("modules_config") or []
                panel_timestamp = status.get("timestamp")
                panel_ok = True
        except Exception as e:
            panel_error = str(e)

    return {
        "baseUrl": base,
        "modes": modes_data.get("modes") or [],
        "currentMode": mode_data.get("current_mode"),
        "boards": boards,
        "modulesConfig": modules_config,
        "panelTimestamp": panel_timestamp,
        "panelOk": panel_ok,
        "panelError": panel_error,
        "location": location,
    }


async def fetch_branch_panel_status(
    branch: dict[str, Any],
    *,
    refresh_hardware: bool = False,
) -> dict[str, Any]:
    """Solo GET /api/panel/status (como el dashboard local). Sin modos tablet."""
    user, password = _require_panel_credentials(branch)
    base = branch_base_url(branch)
    panel_tok = await panel_login(base, user, password)
    async with httpx.AsyncClient(timeout=45.0) as client:
        st = await client.get(
            f"{base}/api/panel/status",
            headers={"Authorization": f"Bearer {panel_tok}"},
            params={"refresh_hardware": str(refresh_hardware).lower()},
        )
    if st.status_code >= 400:
        raise RuntimeError(await _read_error(st))
    status = st.json()
    return {
        "baseUrl": base,
        "boards": status.get("boards") or {},
        "modulesConfig": status.get("modules_config") or [],
        "currentMode": status.get("current_mode"),
        "panelTimestamp": status.get("timestamp"),
        "panelOk": True,
        "panelError": None,
    }


def _require_panel_credentials(branch: dict[str, Any]) -> tuple[str, str]:
    user = (branch.get("usuarioPanel") or "").strip()
    password = branch.get("passwordPanel") or ""
    if not user or not password:
        raise RuntimeError(
            "Configura usuario y contraseña de panel web en la sucursal para operar placas"
        )
    return user, password


async def panel_api_request(
    branch: dict[str, Any],
    method: str,
    path: str,
    *,
    json_body: Any = None,
    params: Optional[dict[str, Any]] = None,
) -> Any:
    """Petición autenticada al panel de la sucursal (`/api/panel/*`)."""
    user, password = _require_panel_credentials(branch)
    base = branch_base_url(branch)
    token = await panel_login(base, user, password)
    url = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.request(
                method.upper(),
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, socket.gaierror, OSError) as e:
        raise RuntimeError(_connection_error_message(base, e)) from e
    if res.status_code >= 400:
        raise RuntimeError(await _read_error(res))
    if res.status_code == 204 or not res.content:
        return {}
    return res.json()


async def branch_health(branch: dict[str, Any]) -> dict[str, Any]:
    base = branch_base_url(branch)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{base}/api/health")
        if res.status_code >= 400:
            return {"reachable": True, "healthy": False, "detail": await _read_error(res)}
        return {"reachable": True, "healthy": True, **(res.json() if res.content else {})}
    except (httpx.ConnectError, httpx.ConnectTimeout, socket.gaierror, OSError) as e:
        return {"reachable": False, "healthy": False, "detail": str(e)}


async def panel_connect_board(branch: dict[str, Any], board_id: int) -> dict[str, Any]:
    return await panel_api_request(
        branch, "POST", f"/api/panel/boards/{board_id}/connect"
    )


async def panel_disconnect_board(branch: dict[str, Any], board_id: int) -> dict[str, Any]:
    return await panel_api_request(
        branch, "POST", f"/api/panel/boards/{board_id}/disconnect"
    )


async def panel_set_output(
    branch: dict[str, Any], board_id: int, channel: int, state: bool
) -> dict[str, Any]:
    return await panel_api_request(
        branch,
        "POST",
        f"/api/panel/boards/{board_id}/output",
        json_body={"channel": channel, "state": state},
    )


async def panel_set_input_override(
    branch: dict[str, Any], board_id: int, channel: int, state: bool
) -> dict[str, Any]:
    return await panel_api_request(
        branch,
        "POST",
        "/api/panel/inputs/override",
        json_body={"board_id": board_id, "channel": channel, "state": state},
    )


async def panel_clear_input_override(
    branch: dict[str, Any], board_id: int, channel: int
) -> dict[str, Any]:
    return await panel_api_request(
        branch,
        "DELETE",
        "/api/panel/inputs/override",
        params={"board_id": board_id, "channel": channel},
    )


async def panel_run_rule(
    branch: dict[str, Any], rule_key: str, *, simulate: bool = False
) -> dict[str, Any]:
    q = "?simulate=true" if simulate else ""
    return await panel_api_request(
        branch, "POST", f"/api/panel/rules/{rule_key}/run{q}"
    )


async def set_branch_mode_rule(branch: dict[str, Any], rule_key: str, active: bool) -> dict[str, Any]:
    base = branch_base_url(branch)
    tablet_tok = await tablet_login(
        base, branch["usuarioTablet"], branch["passwordTablet"]
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{base}/api/v1/set_mode",
            headers={
                "Authorization": f"Bearer {tablet_tok}",
                "Content-Type": "application/json",
            },
            json={"action": "set_rule", "rule_key": rule_key, "active": active},
        )
        if res.status_code >= 400:
            raise RuntimeError(await _read_error(res))
        return res.json()
