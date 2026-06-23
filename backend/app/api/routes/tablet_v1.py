"""API v1 para tablet / integraciones: modos del panel, JWT y usuarios."""
from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, model_validator

from app.api.deps_tablet import get_tablet_username
from app.api.routes import panel
from app.core.config import settings
from app.db import system_events_store as ses
from app.db import tablet_users_store as tus
from app.db.tablet_config_store import get_tablet_config_record
from app.db.schedule_store import get_schedule_config, normalize_location, opening_hours_summary
from app.utils.rule_mode_colors import resolve_rule_color, rule_key_to_label
from app.services import tablet_jwt
from app.services.tablet_password import hash_password, verify_password

router = APIRouter(prefix="/v1", tags=["Tablet API v1"])


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _register_allowed(setup_header: Optional[str]) -> None:
    """
    - Sin TABLET_SETUP_TOKEN: solo el primer usuario puede registrarse sin cabecera.
    - Con TABLET_SETUP_TOKEN: toda alta requiere X-Tablet-Setup-Token coincidente.
    """
    token = (settings.tablet_setup_token or "").strip()
    n = tus.count_users()
    hdr = (setup_header or "").strip()
    if token:
        if hdr != token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cabecera X-Tablet-Setup-Token incorrecta o ausente",
            )
        return
    if n == 0:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Ya existen usuarios: define TABLET_SETUP_TOKEN y envía X-Tablet-Setup-Token para registrar más",
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def auth_register(
    body: RegisterBody,
    x_tablet_setup_token: Annotated[Optional[str], Header(alias="X-Tablet-Setup-Token")] = None,
) -> dict:
    _register_allowed(x_tablet_setup_token)
    if tus.get_user_by_username(body.username):
        raise HTTPException(status_code=409, detail="El usuario ya existe")
    h = hash_password(body.password)
    uid = tus.create_user(body.username, h)
    uname = body.username.strip()
    try:
        ses.record_event(
            "INFO",
            f"Usuario API tablet registrado: {uname}",
            event_type="auth_register",
            source="auth",
            actor_principal="system",
            actor_username=None,
            payload={"user_id": uid, "username": uname},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": uid, "username": uname}


@router.post("/auth/token", response_model=TokenResponse)
def auth_token(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenResponse:
    row = tus.get_user_by_username(form.username)
    if not row or not verify_password(form.password, row[2]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    tok = tablet_jwt.create_access_token(row[1])
    try:
        ses.record_event(
            "INFO",
            f"Login API tablet: {row[1]}",
            event_type="auth_login",
            source="auth",
            actor_principal="tablet",
            actor_username=row[1],
        )
    except Exception:  # noqa: BLE001
        pass
    return TokenResponse(access_token=tok)


@router.get("/modes")
def list_modes(_user: Annotated[str, Depends(get_tablet_username)]) -> dict:
    return {"modes": panel.api_v1_list_modes_from_rules()}


@router.get("/get_mode")
def get_mode(_user: Annotated[str, Depends(get_tablet_username)]) -> dict:
    return {"current_mode": panel.api_v1_get_current_mode()}


@router.get("/tablet-config")
def get_tablet_config(_user: Annotated[str, Depends(get_tablet_username)]) -> dict:
    """Configuración por defecto de la sucursal para tablets."""
    return get_tablet_config_record()


@router.get("/tablet-config/revision")
def get_tablet_config_revision(_user: Annotated[str, Depends(get_tablet_username)]) -> dict:
    rec = get_tablet_config_record()
    return {"revision": rec.get("revision"), "updated_at": rec.get("updated_at")}


@router.get("/branch/location", summary="Ubicación y modo actual (COCE / mapa)")
def get_branch_location(_user: Annotated[str, Depends(get_tablet_username)]) -> dict:
    """Coordenadas, dirección y modo activo con su color. Sin Modbus."""
    cfg = get_schedule_config()
    loc = normalize_location(cfg.get("location"))
    mode_key = panel.api_v1_get_current_mode()
    return {
        **loc,
        "current_mode": mode_key,
        "mode_label": rule_key_to_label(mode_key),
        "mode_color": resolve_rule_color(mode_key, panel.rules_config),
        "opening_hours": opening_hours_summary(cfg),
        "schedules_enabled": bool(cfg.get("enabled")),
    }


class OpenDoorBody(BaseModel):
    door: Literal["p1", "p2"] = Field(description="Puerta a abrir: p1=calle, p2=oficina")


def _open_door_for_tablet(door: str, user: str) -> dict:
    from app.services import zaguan_orchestrator as zo

    door_norm = door.strip().lower()
    if door_norm not in ("p1", "p2"):
        raise HTTPException(status_code=400, detail="Puerta no válida (use p1 o p2)")

    result = zo.open_door_from_tablet(door_norm)  # type: ignore[arg-type]
    if not result.get("ok"):
        reason = str(result.get("reason") or "Apertura rechazada")
        try:
            ses.record_event(
                "WARN",
                f"Apertura tablet {door_norm} rechazada: {reason}",
                event_type="door_open_blocked",
                source="tablet_v1",
                actor_principal="tablet",
                actor_username=user,
                payload={"door": door_norm, "reason": reason},
            )
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": f"No se pudo abrir {door_norm}", "reason": reason},
        )
    try:
        ses.record_event(
            "OK",
            f"Apertura tablet {door_norm}",
            event_type="door_open",
            source="tablet_v1",
            actor_principal="tablet",
            actor_username=user,
            payload=result,
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, **result}


@router.post("/door/open/{door}")
def open_door_by_path(
    door: Literal["p1", "p2"],
    user: Annotated[str, Depends(get_tablet_username)],
) -> dict:
    """
    Abre puerta desde tablet (ruta corta).
    Ej.: POST /api/v1/door/open/p2
    """
    return _open_door_for_tablet(door, user)


@router.post("/door/open")
def open_door(
    body: OpenDoorBody,
    user: Annotated[str, Depends(get_tablet_username)],
) -> dict:
    """
    Abre puerta desde tablet (cuerpo JSON legacy).
    Preferir POST /api/v1/door/open/{door}.
    """
    return _open_door_for_tablet(body.door, user)


class SetModeBody(BaseModel):
    action: Literal["set_rule", "set_output"]
    rule_key: Optional[str] = None
    active: Optional[bool] = None
    code: Optional[str] = None
    on: Optional[bool] = None
    value: Optional[int] = Field(default=None, description="0 u 1 si no se usa on")

    @model_validator(mode="after")
    def _check_action_fields(self) -> SetModeBody:
        if self.action == "set_rule":
            if not self.rule_key or not self.rule_key.strip():
                raise ValueError("rule_key es obligatorio para set_rule")
            if self.active is None:
                raise ValueError("active es obligatorio para set_rule")
        elif self.action == "set_output":
            if not self.code or not self.code.strip():
                raise ValueError("code es obligatorio para set_output")
            if self.on is None and self.value is None:
                raise ValueError("Indica on (bool) o value (0/1) para set_output")
        return self


@router.post("/set_mode")
def set_mode(
    body: SetModeBody,
    _user: Annotated[str, Depends(get_tablet_username)],
) -> dict:
    if body.action == "set_rule":
        rk = body.rule_key.strip()  # type: ignore[union-attr]
        if body.active:
            result = panel.api_v1_execute_rule_for_tablet(rk)
            if result.get("queued"):
                return {
                    "ok": True,
                    "action": "set_rule",
                    "queued": True,
                    "result": result,
                }
            if not bool(result.get("executed", False)):
                reason = str(result.get("reason") or "Regla bloqueada")
                blocked_inputs = result.get("blocked_inputs") or []
                try:
                    ses.record_event(
                        "WARN",
                        f"No se pudo activar modo {rk}: {reason}",
                        event_type="mode_set_blocked",
                        source="tablet_v1",
                        actor_principal="tablet",
                        actor_username=_user,
                        payload={"rule_key": rk, "reason": reason, "blocked_inputs": blocked_inputs},
                    )
                except Exception:  # noqa: BLE001
                    pass
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": f"No se pudo activar el modo {rk}",
                        "reason": reason,
                        "blocked_inputs": blocked_inputs,
                    },
                )
            return {"ok": True, "action": "set_rule", "result": result}
        cleared = panel.api_v1_clear_current_mode_if_match(rk)
        return {"ok": True, "action": "set_rule", "active": False, **cleared}
    code = body.code.strip()  # type: ignore[union-attr]
    on = body.on
    if on is None and body.value is not None:
        if body.value not in (0, 1):
            raise HTTPException(status_code=400, detail="value debe ser 0 o 1")
        on = bool(body.value)
    assert on is not None
    out = panel.api_v1_set_output_by_code(code, on)
    return {"ok": True, "action": "set_output", **out}
