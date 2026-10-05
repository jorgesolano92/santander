"""Endpoints COCE en sucursal (sin abrir Modbus desde HTTP externo salvo heartbeat)."""
from datetime import datetime, timezone

from fastapi import APIRouter

from app.coce.state import build_heartbeat_payload
from app.core.config import settings

router = APIRouter(prefix="/coce", tags=["COCE sucursal"])


@router.get("/heartbeat", summary="Heartbeat sucursal para COCE")
def coce_heartbeat():
    """
    Estado real Modbus/modo para el canal COCE.
    A diferencia de /api/ping, incluye placas conectadas y modo activo.
    """
    payload = build_heartbeat_payload()
    return {
        "ok": True,
        "scope": "coce_heartbeat",
        "installation_id": settings.coce_installation_id or None,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
