from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api.deps import get_client_ip, get_current_username
from app.db import audit_store as audit
from app.db import branches_store as branches
from app.services import branch_proxy

router = APIRouter(prefix="/branches", tags=["Operaciones sucursal"])


class SetModeBody(BaseModel):
    rule_key: str = Field(min_length=1)
    active: bool = True


class OutputBody(BaseModel):
    channel: int = Field(ge=1, le=12)
    state: bool


class InputOverrideBody(BaseModel):
    channel: int = Field(ge=1, le=12)
    state: Optional[bool] = Field(
        default=None,
        description="true/false forzar; null = limpiar override (REAL)",
    )


def _branch_or_404(branch_id: str) -> dict:
    branch = branches.get_branch(branch_id, internal=True)
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return branch


async def _audit_panel_op(
    *,
    request: Request,
    user: str,
    branch_id: str,
    branch: dict,
    action: str,
    success: bool,
    detail: dict,
) -> None:
    audit.record_audit(
        actor_username=user,
        action=action,
        branch_id=branch_id,
        branch_nombre=branch["nombre"],
        success=success,
        detail=detail,
        ip_address=get_client_ip(request),
    )


@router.get("/{branch_id}/snapshot")
async def snapshot(
    branch_id: str,
    request: Request,
    refresh_hardware: bool = Query(
        False,
        description="Si true, relee Modbus en sucursal (lento). Por defecto RAM como dashboard local.",
    ),
    user: str = Depends(get_current_username),
) -> dict:
    branch = _branch_or_404(branch_id)
    try:
        data = await branch_proxy.fetch_branch_snapshot(
            branch, refresh_hardware=refresh_hardware
        )
        audit.record_audit(
            actor_username=user,
            action="branch.snapshot",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=True,
            ip_address=get_client_ip(request),
        )
        return {"branchId": branch_id, **data}
    except Exception as e:
        audit.record_audit(
            actor_username=user,
            action="branch.snapshot",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=False,
            detail={"error": str(e)},
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{branch_id}/panel-status")
async def panel_status(
    branch_id: str,
    request: Request,
    refresh_hardware: bool = Query(
        False,
        description="Igual que /api/panel/status en sucursal (false = rápido, estado en RAM).",
    ),
    user: str = Depends(get_current_username),
) -> dict:
    """Solo estado panel (IN/OUT/modo). Misma respuesta que el dashboard local, sin modos tablet."""
    branch = _branch_or_404(branch_id)
    try:
        data = await branch_proxy.fetch_branch_panel_status(
            branch, refresh_hardware=refresh_hardware
        )
        audit.record_audit(
            actor_username=user,
            action="branch.panel_status",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=True,
            ip_address=get_client_ip(request),
        )
        return {"branchId": branch_id, **data}
    except Exception as e:
        audit.record_audit(
            actor_username=user,
            action="branch.panel_status",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=False,
            detail={"error": str(e)},
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{branch_id}/panel-stats")
async def panel_stats(
    branch_id: str,
    request: Request,
    from_ts: Optional[str] = Query(default=None, alias="from"),
    to_ts: Optional[str] = Query(default=None, alias="to"),
    export: Optional[str] = Query(default=None),
    user: str = Depends(get_current_username),
) -> Any:
    """Resumen operativo de la sucursal (pulsaciones + eventos)."""
    branch = _branch_or_404(branch_id)
    params: dict[str, Any] = {}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts
    if export:
        params["export"] = export
    try:
        data = await branch_proxy.panel_api_request(
            branch,
            "GET",
            "/api/panel/stats",
            params=params or None,
            as_text=bool(export and str(export).lower() == "csv"),
        )
        audit.record_audit(
            actor_username=user,
            action="branch.panel_stats",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=True,
            ip_address=get_client_ip(request),
        )
        if export and str(export).lower() == "csv":
            return PlainTextResponse(
                str(data or ""),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="stats-{branch_id}.csv"'
                },
            )
        if isinstance(data, dict):
            return {"branchId": branch_id, "branchNombre": branch["nombre"], **data}
        return data
    except Exception as e:
        audit.record_audit(
            actor_username=user,
            action="branch.panel_stats",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=False,
            detail={"error": str(e)},
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{branch_id}/location")
async def branch_location(
    branch_id: str,
    request: Request,
    user: str = Depends(get_current_username),
) -> dict:
    """Ubicación de la sucursal (lat/long/dirección) vía API tablet de la oficina."""
    branch = _branch_or_404(branch_id)
    try:
        location = await branch_proxy.fetch_branch_location(branch)
        audit.record_audit(
            actor_username=user,
            action="branch.location",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=True,
            ip_address=get_client_ip(request),
        )
        return {"branchId": branch_id, "location": location}
    except Exception as e:
        audit.record_audit(
            actor_username=user,
            action="branch.location",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=False,
            detail={"error": str(e)},
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{branch_id}/health")
async def branch_health(
    branch_id: str,
    _user: str = Depends(get_current_username),
) -> dict:
    branch = _branch_or_404(branch_id)
    return await branch_proxy.branch_health(branch)


@router.post("/{branch_id}/set-mode")
async def set_mode(
    branch_id: str,
    body: SetModeBody,
    request: Request,
    user: str = Depends(get_current_username),
) -> dict:
    branch = _branch_or_404(branch_id)
    try:
        result = await branch_proxy.set_branch_mode_rule(
            branch, body.rule_key.strip(), body.active
        )
        audit.record_audit(
            actor_username=user,
            action="branch.set_mode",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=True,
            detail={"rule_key": body.rule_key, "active": body.active},
            ip_address=get_client_ip(request),
        )
        return {"ok": True, "result": result}
    except Exception as e:
        audit.record_audit(
            actor_username=user,
            action="branch.set_mode",
            branch_id=branch_id,
            branch_nombre=branch["nombre"],
            success=False,
            detail={"rule_key": body.rule_key, "error": str(e)},
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/{branch_id}/panel/boards/{board_id}/connect")
async def panel_connect(
    branch_id: str,
    board_id: int,
    request: Request,
    user: str = Depends(get_current_username),
) -> dict:
    branch = _branch_or_404(branch_id)
    try:
        result = await branch_proxy.panel_connect_board(branch, board_id)
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.connect",
            success=True,
            detail={"board_id": board_id},
        )
        return {"ok": True, "result": result}
    except Exception as e:
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.connect",
            success=False,
            detail={"board_id": board_id, "error": str(e)},
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/{branch_id}/panel/boards/{board_id}/disconnect")
async def panel_disconnect(
    branch_id: str,
    board_id: int,
    request: Request,
    user: str = Depends(get_current_username),
) -> dict:
    branch = _branch_or_404(branch_id)
    try:
        result = await branch_proxy.panel_disconnect_board(branch, board_id)
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.disconnect",
            success=True,
            detail={"board_id": board_id},
        )
        return {"ok": True, "result": result}
    except Exception as e:
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.disconnect",
            success=False,
            detail={"board_id": board_id, "error": str(e)},
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/{branch_id}/panel/boards/{board_id}/output")
async def panel_output(
    branch_id: str,
    board_id: int,
    body: OutputBody,
    request: Request,
    user: str = Depends(get_current_username),
) -> dict:
    branch = _branch_or_404(branch_id)
    try:
        result = await branch_proxy.panel_set_output(
            branch, board_id, body.channel, body.state
        )
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.output",
            success=True,
            detail={"board_id": board_id, "channel": body.channel, "state": body.state},
        )
        return {"ok": True, "result": result}
    except Exception as e:
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.output",
            success=False,
            detail={"board_id": board_id, "error": str(e)},
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/{branch_id}/panel/boards/{board_id}/input-override")
async def panel_input_override(
    branch_id: str,
    board_id: int,
    body: InputOverrideBody,
    request: Request,
    user: str = Depends(get_current_username),
) -> dict:
    branch = _branch_or_404(branch_id)
    try:
        if body.state is None:
            result = await branch_proxy.panel_clear_input_override(
                branch, board_id, body.channel
            )
        else:
            result = await branch_proxy.panel_set_input_override(
                branch, board_id, body.channel, body.state
            )
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.input_override",
            success=True,
            detail={"board_id": board_id, "channel": body.channel, "state": body.state},
        )
        return {"ok": True, "result": result}
    except Exception as e:
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.input_override",
            success=False,
            detail={"board_id": board_id, "error": str(e)},
        )
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/{branch_id}/panel/rules/{rule_key}/run")
async def panel_run_rule(
    branch_id: str,
    rule_key: str,
    request: Request,
    user: str = Depends(get_current_username),
    simulate: bool = Query(False, description="Si true, no escribe salidas en hardware"),
) -> dict:
    branch = _branch_or_404(branch_id)
    try:
        result = await branch_proxy.panel_run_rule(
            branch, rule_key.strip(), simulate=simulate
        )
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.run_rule",
            success=True,
            detail={"rule_key": rule_key, "simulate": simulate},
        )
        return {"ok": True, "result": result}
    except Exception as e:
        await _audit_panel_op(
            request=request,
            user=user,
            branch_id=branch_id,
            branch=branch,
            action="branch.panel.run_rule",
            success=False,
            detail={"rule_key": rule_key, "error": str(e)},
        )
        raise HTTPException(status_code=502, detail=str(e)) from e
