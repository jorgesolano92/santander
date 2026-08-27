"""Esquemas alineados con CSIP custom1 OpenAPI v1.1.0."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ButtonId = Literal["p1", "p2", "push", "5"]
LedId = Literal["p1", "p2", "ALL"]
LedEstado = Literal[
    "libre",
    "ocupado",
    "abriendo",
    "apagado",
    "green",
    "red",
    "orange",
    "off",
    "rainbow",
]
CallTargetType = Literal["number", "ip", "default"]
NotifyCanal = Literal["p1", "p2"]


class ButtonEventRequest(BaseModel):
    button_id: ButtonId
    meta: Optional[dict[str, Any]] = None


class CallStartRequest(BaseModel):
    target_type: Optional[CallTargetType] = None
    target: Optional[str] = None
    ip: Optional[str] = None
    user: Optional[str] = None
    recording: Optional[bool] = None
    rec: Optional[bool] = None


class LedControlRequest(BaseModel):
    cmd: Optional[str] = None
    led: Optional[LedId] = None
    estado: Optional[LedEstado] = None
    brightness: Optional[int] = Field(default=None, ge=1, le=9)


class CsipNotifyAck(BaseModel):
    ok: bool = True
    canal: NotifyCanal
    forwarded_to_zaguan: bool = False
    received_at: str
    body: dict[str, Any] = Field(default_factory=dict)


class CsipStatusResponse(BaseModel):
    enabled: bool
    base_url_configured: bool
    base_url: Optional[str] = None
    api_token_configured: bool
    webhook_token_required: bool
    forward_pulsacion_to_zaguan: bool
    timeout_s: float
    recent_notifications: list[dict[str, Any]] = Field(default_factory=list)
