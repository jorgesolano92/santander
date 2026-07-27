"""Configuración COCE API central."""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV = _ROOT / ".env"
_CFG: dict = {"env_file_encoding": "utf-8", "extra": "ignore", "env_prefix": "COCE_"}
if _ENV.is_file():
    _CFG["env_file"] = str(_ENV)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(**_CFG)

    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9000
    app_name: str = "COCE API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/coce"

    database_url: str = f"sqlite:///{(_ROOT / 'data' / 'coce.db').as_posix()}"

    jwt_secret: str = "cambiar-en-produccion-coce-jwt"
    jwt_expire_minutes: int = 480
    secrets_key: Optional[str] = None
    setup_token: Optional[str] = None

    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    # true = acepta cualquier Origin (solo dev / redes variables tipo ZeroTier). No usar en producción.
    cors_allow_all: bool = False

    # WebSocket ingest sucursal → COCE (API key por sucursal)
    branch_auth_required: bool = True
    branch_heartbeat_timeout_seconds: int = 120
    # Checkout local del código de panel sucursal (backend/ + frontend/) para from-local
    panel_source_dir: str = ""
    updates_max_upload_mb: int = 256

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
