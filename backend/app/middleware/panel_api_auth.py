"""Exige JWT de panel en /api salvo rutas públicas (auth, health, ping, tablet v1, …)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.request_context import reset_actor, set_actor
from app.services import panel_jwt


def _api_base() -> str:
    p = (settings.api_prefix or "/api").rstrip("/") or "/api"
    return p


def _is_public_api_path(path: str) -> bool:
    base = _api_base()
    if path == f"{base}/health":
        return True
    if path == f"{base}/ping":
        return True
    if path == f"{base}/status":
        return True
    if path == f"{base}/panel/ws/live":
        return True
    if path == f"{base}/panel/diagnostics/rtu-ping":
        return True
    if path.startswith(f"{base}/auth/"):
        return True
    if path.startswith(f"{base}/v1/"):
        return True
    if path.startswith(f"{base}/zaguan/"):
        return True
    # Webhooks CSIP (placa → app) y health del módulo; el resto /csip/* exige JWT panel.
    if path == f"{base}/csip/health":
        return True
    if path == f"{base}/csip/notify" or path.startswith(f"{base}/csip/notify/"):
        return True
    return False


class PanelApiAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        base = _api_base()
        if request.method == "OPTIONS":
            return await call_next(request)
        if not path.startswith(f"{base}/") and path != base:
            return await call_next(request)
        if _is_public_api_path(path):
            return await call_next(request)

        auth = request.headers.get("Authorization")
        if not auth or not auth.lower().startswith("bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Falta Authorization: Bearer <token>"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = auth[7:].strip()
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Falta Authorization: Bearer <token>"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            username = panel_jwt.decode_access_token_username(token)
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token inválido o expirado"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.panel_username = username
        tok = set_actor("panel", username)
        try:
            return await call_next(request)
        finally:
            reset_actor(tok)
