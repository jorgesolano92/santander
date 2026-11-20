"""API de enrutado de pulsaciones (llamada tablet vs apertura)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db import call_routing_store

router = APIRouter(prefix="/panel/call-routing", tags=["Call routing"])


class CallRoutingBody(BaseModel):
    overrides: dict[str, dict[str, str]] = Field(default_factory=dict)


def _no_zaguan_flag() -> bool:
    return bool(getattr(settings, "extendido_p1_tablet_call_without_zaguan", False))


@router.get("")
def get_call_routing() -> dict[str, Any]:
    return call_routing_store.public_status(
        extendido_p1_call_without_zaguan=_no_zaguan_flag()
    )


@router.put("")
def put_call_routing(body: CallRoutingBody) -> dict[str, Any]:
    try:
        call_routing_store.set_overrides(body.overrides or {})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e
    return call_routing_store.public_status(
        extendido_p1_call_without_zaguan=_no_zaguan_flag()
    )
