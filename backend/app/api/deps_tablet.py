"""Dependencias FastAPI: usuario autenticado vía Bearer JWT (tablet v1)."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import authorized_tablets_store as ats
from app.services import tablet_jwt

_security = HTTPBearer(auto_error=False)


def get_tablet_username(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    x_tablet_id: Optional[str] = Header(default=None, alias="X-Tablet-Id"),
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        username = tablet_jwt.decode_access_token_username(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    # Con autorización exigida, una tablet identificada debe estar activa en el panel.
    if (x_tablet_id or "").strip() and ats.get_settings().get("enforcement_enabled"):
        row = ats.get_by_android_id(x_tablet_id)
        if not row or not row.get("enabled"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tablet no autorizada")
    return username
