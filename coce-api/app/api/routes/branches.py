from __future__ import annotations

import uuid
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_client_ip, get_current_username
from app.db import audit_store as audit
from app.db import branches_store as branches
from app.services.host_utils import normalize_host, validate_host

router = APIRouter(prefix="/branches", tags=["Sucursales"])


def _host_from_body(raw: str) -> str:
    host = normalize_host(raw)
    try:
        validate_host(host)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return host


class BranchBody(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535, default=8000)
    useHttps: bool = False
    usuarioTablet: str = Field(min_length=1, max_length=64)
    passwordTablet: Optional[str] = Field(default=None, min_length=1, max_length=128)
    usuarioPanel: Optional[str] = Field(default=None, max_length=64)
    passwordPanel: Optional[str] = Field(default=None, max_length=128)
    estado: Literal["operativo", "no_operativo", "apagado"] = "operativo"


class BranchCreateBody(BranchBody):
    passwordTablet: str = Field(min_length=1, max_length=128)


@router.get("")
def list_all(_user: Annotated[str, Depends(get_current_username)]) -> dict:
    return {"branches": branches.list_branches()}


@router.get("/{branch_id}")
def get_one(
    branch_id: str,
    _user: Annotated[str, Depends(get_current_username)],
) -> dict:
    row = branches.get_branch(branch_id)
    if not row:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return row


@router.post("", status_code=201)
def create(
    body: BranchCreateBody,
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
) -> dict:
    bid = str(uuid.uuid4())
    data = {
        "id": bid,
        "nombre": body.nombre.strip(),
        "host": _host_from_body(body.host),
        "port": body.port,
        "useHttps": body.useHttps,
        "usuarioTablet": body.usuarioTablet.strip(),
        "passwordTablet": body.passwordTablet,
        "usuarioPanel": (body.usuarioPanel or "").strip() or None,
        "passwordPanel": body.passwordPanel or "",
        "estado": body.estado,
    }
    row, ingest_token = branches.create_branch(data)
    audit.record_audit(
        actor_username=user,
        action="branch.create",
        branch_id=bid,
        branch_nombre=row["nombre"],
        detail={"host": row["host"], "port": row["port"]},
        ip_address=get_client_ip(request),
    )
    return {**row, "ingestToken": ingest_token}


@router.put("/{branch_id}")
def update(
    branch_id: str,
    body: BranchBody,
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
) -> dict:
    existing = branches.get_branch(branch_id, internal=True)
    if not existing:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    if not body.passwordTablet:
        pw_tablet = existing["passwordTablet"]
    else:
        pw_tablet = body.passwordTablet
    data = {
        "nombre": body.nombre.strip(),
        "host": _host_from_body(body.host),
        "port": body.port,
        "useHttps": body.useHttps,
        "usuarioTablet": body.usuarioTablet.strip(),
        "passwordTablet": pw_tablet,
        "usuarioPanel": (body.usuarioPanel or "").strip() or None,
        "passwordPanel": body.passwordPanel if body.passwordPanel is not None else existing.get("passwordPanel"),
        "estado": body.estado,
    }
    row = branches.update_branch(branch_id, data)
    assert row is not None
    audit.record_audit(
        actor_username=user,
        action="branch.update",
        branch_id=branch_id,
        branch_nombre=row["nombre"],
        ip_address=get_client_ip(request),
    )
    return row


@router.delete("/{branch_id}", status_code=204)
def delete(
    branch_id: str,
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
) -> None:
    existing = branches.get_branch(branch_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    branches.delete_branch(branch_id)
    audit.record_audit(
        actor_username=user,
        action="branch.delete",
        branch_id=branch_id,
        branch_nombre=existing["nombre"],
        ip_address=get_client_ip(request),
    )
