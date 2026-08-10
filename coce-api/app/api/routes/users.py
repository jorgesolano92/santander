from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_client_ip, require_admin
from app.db import audit_store as audit
from app.db import users_store as users
from app.services.password import hash_password

router = APIRouter(prefix="/users", tags=["Usuarios COCE"])


class CreateUserBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "operador"] = "operador"


class UpdateUserBody(BaseModel):
    role: Optional[Literal["admin", "operador"]] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


@router.get("")
def list_users(_admin: Annotated[CurrentUser, Depends(require_admin)]) -> dict:
    return {"users": users.list_users()}


@router.post("", status_code=201)
def create_user(
    body: CreateUserBody,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict:
    if users.get_user_by_username(body.username):
        raise HTTPException(status_code=409, detail="El usuario ya existe")
    uid = users.create_user(
        body.username,
        hash_password(body.password),
        role=body.role,
    )
    audit.record_audit(
        actor_username=admin.username,
        action="user.create",
        success=True,
        detail={"user_id": uid, "username": body.username.strip(), "role": body.role},
        ip_address=get_client_ip(request),
    )
    return {
        "id": uid,
        "username": body.username.strip(),
        "role": body.role,
    }


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    body: UpdateUserBody,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict:
    if body.role is None and body.password is None:
        raise HTTPException(status_code=400, detail="Nada que actualizar")
    pwd = hash_password(body.password) if body.password else None
    row = users.update_user(user_id, role=body.role, password_hash=pwd)
    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    audit.record_audit(
        actor_username=admin.username,
        action="user.update",
        success=True,
        detail={"user_id": user_id, "role": body.role, "password_changed": bool(pwd)},
        ip_address=get_client_ip(request),
    )
    return row


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict:
    if admin.uid is not None and admin.uid == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    existing = users.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # Evitar quedarse sin admins
    if existing[3] == "admin":
        admins = [u for u in users.list_users() if u["role"] == "admin"]
        if len(admins) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Debe quedar al menos un usuario admin",
            )
    ok = users.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    audit.record_audit(
        actor_username=admin.username,
        action="user.delete",
        success=True,
        detail={"user_id": user_id, "username": existing[1]},
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "id": user_id}
