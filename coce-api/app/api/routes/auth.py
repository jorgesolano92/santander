from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db import audit_store as audit
from app.db import users_store as users
from app.api.deps import CurrentUser, get_client_ip, get_current_user, get_current_username
from app.services import jwt_service
from app.services.password import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth COCE"])


class AuthBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _register_allowed(setup_header: Optional[str]) -> None:
    token = (settings.setup_token or "").strip()
    n = users.count_users()
    hdr = (setup_header or "").strip()
    if token:
        if hdr != token:
            raise HTTPException(
                status_code=403,
                detail="Cabecera X-Coce-Setup-Token incorrecta o ausente",
            )
        return
    if n == 0:
        return
    raise HTTPException(
        status_code=403,
        detail="Ya existen usuarios COCE: define COCE_SETUP_TOKEN para registrar más",
    )


@router.post("/register", status_code=201)
def register(
    body: AuthBody,
    request: Request,
    x_coce_setup_token: Annotated[Optional[str], Header(alias="X-Coce-Setup-Token")] = None,
) -> dict:
    _register_allowed(x_coce_setup_token)
    if users.get_user_by_username(body.username):
        raise HTTPException(status_code=409, detail="El usuario ya existe")
    # Primer usuario = admin; siguientes vía setup token = operador.
    role = "admin" if users.count_users() == 0 else "operador"
    uid = users.create_user(body.username, hash_password(body.password), role=role)
    uname = body.username.strip()
    audit.record_audit(
        actor_username=uname,
        action="auth.register",
        success=True,
        detail={"user_id": uid, "role": role},
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "id": uid, "username": uname, "role": role}


@router.post("/login", response_model=TokenResponse)
def login(body: AuthBody, request: Request) -> TokenResponse:
    row = users.get_user_by_username(body.username)
    if not row or not verify_password(body.password, row[2]):
        audit.record_audit(
            actor_username=body.username.strip(),
            action="auth.login",
            success=False,
            detail={"reason": "credenciales_invalidas"},
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    uname = row[1]
    role = row[3]
    tok = jwt_service.create_access_token(uname, {"uid": row[0], "role": role})
    audit.record_audit(
        actor_username=uname,
        action="auth.login",
        success=True,
        detail={"role": role},
        ip_address=get_client_ip(request),
    )
    return TokenResponse(access_token=tok)


@router.get("/setup-status")
def setup_status() -> dict:
    """Público: indica si el front debe mostrar registro de nuevos administradores."""
    n = users.count_users()
    token = (settings.setup_token or "").strip()
    has_users = n > 0
    return {
        "hasUsers": has_users,
        "allowRegister": not has_users or bool(token),
        "requiresSetupToken": has_users and bool(token),
    }


@router.get("/me")
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict:
    return {"id": user.uid, "username": user.username, "role": user.role}
