"""Configuración y prueba de locuciones (relés del reproductor de audio)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import locution_store
from app.services import locution_service

router = APIRouter(prefix="/panel/locutions", tags=["Locuciones"])


class LocutionsBody(BaseModel):
    triggers: list[dict[str, Any]]


class LocutionTestBody(BaseModel):
    output: str
    pulse_seconds: float = Field(default=1.0, ge=locution_store.PULSE_MIN_S, le=locution_store.PULSE_MAX_S)


def _modes() -> list[dict[str, str]]:
    try:
        from app.api.routes import panel
        from app.utils.rule_mode_colors import rule_key_to_label

        return [
            {"key": m["key"], "label": rule_key_to_label(m["key"])}
            for m in panel.api_v1_list_modes_from_rules()
            if str(m.get("key") or "").startswith("horario_")
        ]
    except Exception:  # noqa: BLE001
        return []


@router.get("")
def get_locutions() -> dict:
    return {
        "triggers": locution_store.get_triggers(),
        "outputs": [{"code": c, "label": l} for c, l in locution_store.LOCUTION_OUTPUTS.items()],
        "modes": _modes(),
    }


@router.put("")
def put_locutions(body: LocutionsBody) -> dict:
    try:
        triggers = locution_store.set_triggers(body.triggers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "triggers": triggers}


@router.post("/test")
def test_locution(body: LocutionTestBody) -> dict:
    try:
        started = locution_service.play(body.output, body.pulse_seconds, reason="prueba desde panel")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not started:
        raise HTTPException(status_code=409, detail="Esa locución ya se está reproduciendo")
    return {"ok": True}
