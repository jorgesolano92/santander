"""GET/PUT /api/config/* — horarios, festivos, tiempos, boards (IPs ETD8A12)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Body, HTTPException
from pydantic import BaseModel, Field
from app.hardware.modbus_client import get_boards_config_placeholder, test_board_ports
from app.db.template_store import get_template_config, set_template_config
from app.db.tablet_config_store import get_tablet_config_record, set_tablet_config
from app.db.schedule_store import get_schedule_config, set_schedule_config
from app.db import authorized_tablets_store as ats
from app.services.schedule_runner import notify_schedule_config_changed

router = APIRouter(prefix="/config")


class AuthorizedTabletCreate(BaseModel):
    android_id: str = Field(min_length=1, max_length=128)
    label: str = Field(default="", max_length=120)


class AuthorizedTabletUpdate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=120)
    enabled: Optional[bool] = None


class AuthorizedTabletsSettingsBody(BaseModel):
    enforcement_enabled: bool


@router.get("/template", summary="Obtener configuración de la plantilla")
def get_template():
    return get_template_config()


@router.put("/template", summary="Actualizar configuración de la plantilla")
def put_template(config: dict = Body(...)):
    set_template_config(config)
    return {"ok": True}


@router.get("/tablet", summary="Configuración por defecto de tablets (sucursal)")
def get_tablet():
    return get_tablet_config_record()


@router.put("/tablet", summary="Guardar configuración por defecto de tablets")
def put_tablet(config: dict = Body(...)):
    result = set_tablet_config(config)
    return {**result, "config": config}


@router.get("/authorized-tablets", summary="Listar tablets autorizadas (Android ID)")
def list_authorized_tablets():
    return {
        "settings": ats.get_settings(),
        "items": ats.list_tablets(),
    }


@router.put("/authorized-tablets/settings", summary="Activar/desactivar exigencia de autorización")
def put_authorized_tablets_settings(body: AuthorizedTabletsSettingsBody):
    return ats.set_enforcement_enabled(body.enforcement_enabled)


@router.post("/authorized-tablets", summary="Autorizar una tablet por Android ID")
def create_authorized_tablet(body: AuthorizedTabletCreate):
    try:
        item = ats.add_tablet(body.android_id, body.label)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "item": item}


@router.put("/authorized-tablets/{tablet_id}", summary="Actualizar tablet autorizada")
def update_authorized_tablet(tablet_id: int, body: AuthorizedTabletUpdate):
    item = ats.update_tablet(tablet_id, label=body.label, enabled=body.enabled)
    if not item:
        raise HTTPException(status_code=404, detail="Tablet no encontrada")
    return {"ok": True, "item": item}


@router.delete("/authorized-tablets/{tablet_id}", summary="Eliminar tablet autorizada")
def delete_authorized_tablet(tablet_id: int):
    if not ats.delete_tablet(tablet_id):
        raise HTTPException(status_code=404, detail="Tablet no encontrada")
    return {"ok": True}


@router.get("/schedules", summary="Configuración de horarios semanales")
def get_schedules():
    return get_schedule_config()


@router.put("/schedules", summary="Actualizar horarios semanales")
def put_schedules(config: dict = Body(...)):
    loc = config.get("location") if isinstance(config, dict) else None
    if isinstance(loc, dict):
        lat, lng = loc.get("latitude"), loc.get("longitude")
        for label, val, lo, hi in (
            ("latitude", lat, -90.0, 90.0),
            ("longitude", lng, -180.0, 180.0),
        ):
            if val is None or val == "":
                continue
            try:
                n = float(val)
            except (TypeError, ValueError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"location.{label} debe ser numérico",
                ) from e
            if not lo <= n <= hi:
                raise HTTPException(
                    status_code=400,
                    detail=f"location.{label} fuera de rango ({lo}…{hi})",
                )
    result = set_schedule_config(config)
    notify_schedule_config_changed()
    return result


@router.get("/holidays", summary="Calendario de festivos")
def get_holidays():
    """(TODO: tabla holidays.)"""
    return {"holidays": []}


@router.post("/holidays", summary="Añadir festivo")
def post_holiday():
    return {"id": 1}


@router.delete("/holidays/{holiday_id}", summary="Eliminar festivo")
def delete_holiday(holiday_id: int):
    return {"deleted": holiday_id}


@router.get("/timings", summary="Tiempos (retardos, pulsos)")
def get_timings():
    """(TODO: tabla config_timings.)"""
    return {"timings": {}}


@router.put("/timings", summary="Actualizar tiempos")
def put_timings():
    return {"ok": True}


@router.get("/boards", summary="Configuración módulos ETD8A12")
def get_boards():
    """IP, puerto, slave_id de los 3 módulos. (TODO: tabla boards_config.)"""
    boards_cfg = get_boards_config_placeholder()
    return {
        "boards": [
            {"board_id": board_id, **cfg}
            for board_id, cfg in boards_cfg.items()
        ]
    }


@router.put("/boards", summary="Actualizar configuración de módulos")
def put_boards():
    """(TODO: validar y guardar en boards_config; reconectar Modbus.)"""
    return {"ok": True}


@router.get("/boards/test-connection", summary="Diagnóstico de conectividad ETD8A12")
def test_boards_connection(
    timeout: float = Query(default=2.0, ge=0.5, le=10.0),
):
    """
    Prueba conectividad TCP a las IPs de ETD8A12.
    Se prueba el puerto configurado y puertos típicos de diagnóstico.
    """
    ports_to_check = [5000, 502, 80, 443, 23]
    boards_cfg = get_boards_config_placeholder()
    diagnostics = []

    for board_id, cfg in boards_cfg.items():
        host = cfg["host"]
        report = test_board_ports(host=host, ports=ports_to_check, timeout=timeout)
        diagnostics.append(
            {
                "board_id": board_id,
                "name": cfg["name"],
                "host": host,
                "configured_port": cfg["port"],
                "modbus_configured_reachable": any(
                    c["port"] == cfg["port"] and c["reachable"] for c in report["checks"]
                ),
                "open_ports": report["open_ports"],
                "checks": report["checks"],
            }
        )

    return {
        "ok": True,
        "timeout_seconds": timeout,
        "tested_ports": ports_to_check,
        "boards": diagnostics,
    }
