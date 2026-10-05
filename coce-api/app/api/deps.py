from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import users_store as users
from app.services.jwt_service import decode_token

_bearer = HTTPBearer(auto_error=False)

CoceRole = Literal["admin", "operador"]


@dataclass(frozen=True)
class CurrentUser:
    username: str
    uid: Optional[int]
    role: CoceRole


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(creds.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Token inválido")
    role: CoceRole = "operador"
    uid: Optional[int] = None
    row = users.get_user_by_username(sub)
    if row:
        uid = row[0]
        role = row[3] if row[3] in ("admin", "operador") else "operador"
    else:
        claim_role = str(payload.get("role") or "operador").lower()
        role = "admin" if claim_role == "admin" else "operador"
        raw_uid = payload.get("uid")
        try:
            uid = int(raw_uid) if raw_uid is not None else None
        except (TypeError, ValueError):
            uid = None
    return CurrentUser(username=sub, uid=uid, role=role)


def get_current_username(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> str:
    return user.username


def require_admin(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requiere rol admin",
        )
    return user
