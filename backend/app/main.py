"""
Aplicación principal FastAPI — Control de Accesos (Santander / SAIMA).
Arranque: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import BASE_DIR, settings
from app.api.routes import health, status, modes, events, config, panel, panel_ws, tablet_v1, tablet_ws, auth_panel, coce_status
from app.csip.routes import router as csip_router
from app.coce.client import start_coce_client_task
from app.services import panel_live_hub, tablet_call_hub
from app.db import system_events_store as ses
from app.middleware.panel_api_auth import PanelApiAuthMiddleware
from app.middleware.tablet_actor_context import TabletActorContextMiddleware
from zaguan_esp32 import registrar_callback_pulsacion, router as zaguan_esp32_router
from app.services import zaguan_orchestrator
from app.services.schedule_runner import schedule_background_loop

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("control_accesos")

async def _events_retention_loop() -> None:
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            n = ses.purge_events_older_than()
            if n:
                log.info("Retención system_events: eliminadas %s filas", n)
        except Exception as e:  # noqa: BLE001
            log.warning("Purge system_events: %s", e)


async def _auto_rules_background_loop() -> None:
    interval_s = max(0.15, float(settings.auto_rules_background_interval_seconds))
    while True:
        await asyncio.sleep(interval_s)
        try:
            # El ciclo hace I/O Modbus síncrono (RTU especialmente lento): en hilo aparte
            # para no bloquear el bucle asyncio (API /ping, SPA, etc.).
            await asyncio.to_thread(
                panel.background_auto_rules_cycle,
                deactivate_on_fall=bool(settings.auto_rules_deactivate_on_fall),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Ciclo auto-rules background: %s", e)


async def _zaguan_door_sensors_loop() -> None:
    """Sensores de puerta + LEDs zaguán: separado del ciclo de IN/reglas (no bloquear Modbus)."""
    interval_s = max(0.15, float(settings.zaguan_door_poll_interval_seconds))
    while True:
        await asyncio.sleep(interval_s)
        try:
            await asyncio.to_thread(zaguan_orchestrator.poll_door_sensors)
        except Exception as e:  # noqa: BLE001
            log.warning("Poll sensores puerta zaguán: %s", e)


async def _on_zaguan_pulsacion(canal: str, ts: int) -> None:
    """Orquestador zaguán: LEDs + apertura según modo (automático / autoservicio)."""
    log.info("Pulsación zaguán recibida: canal=%s ts=%s", canal, ts)
    if canal not in ("p1", "p2", "p3", "p4"):
        log.warning("Canal zaguán no válido: %s", canal)
        return
    return await zaguan_orchestrator.handle_pulsacion(canal, ts)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicio y cierre: conexión BD, polling Modbus, etc."""
    log.info("Iniciando servicio Control de Accesos")
    zaguan_orchestrator.bind_async_loop(asyncio.get_running_loop())
    panel_live_pump = asyncio.create_task(panel_live_hub.pump_loop())
    tablet_ws_pump = asyncio.create_task(tablet_call_hub.pump_loop())
    try:
        ses.ensure_system_events_schema()
        n0 = ses.purge_events_older_than()
        if n0:
            log.info("Retención system_events (arranque): eliminadas %s filas", n0)
    except Exception as e:  # noqa: BLE001
        log.warning("system_events al arranque: %s", e)
    registrar_callback_pulsacion(_on_zaguan_pulsacion)
    try:
        zaguan_orchestrator.bootstrap_from_panel()
    except Exception as e:  # noqa: BLE001
        log.warning("Bootstrap orquestador zaguán: %s", e)
    retention_task = asyncio.create_task(_events_retention_loop())
    schedule_task = asyncio.create_task(schedule_background_loop())
    auto_rules_task: Optional[asyncio.Task] = None
    if settings.auto_rules_background_enabled:
        auto_rules_task = asyncio.create_task(_auto_rules_background_loop())
    door_sensors_task = asyncio.create_task(_zaguan_door_sensors_loop())
    coce_ws_task: Optional[asyncio.Task] = start_coce_client_task()
    yield
    panel_live_pump.cancel()
    tablet_ws_pump.cancel()
    retention_task.cancel()
    schedule_task.cancel()
    if auto_rules_task:
        auto_rules_task.cancel()
    door_sensors_task.cancel()
    if coce_ws_task:
        coce_ws_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        pass
    try:
        await schedule_task
    except asyncio.CancelledError:
        pass
    if auto_rules_task:
        try:
            await auto_rules_task
        except asyncio.CancelledError:
            pass
    try:
        await door_sensors_task
    except asyncio.CancelledError:
        pass
    if coce_ws_task:
        try:
            await coce_ws_task
        except asyncio.CancelledError:
            pass
    try:
        await tablet_ws_pump
    except asyncio.CancelledError:
        pass
    try:
        await panel_live_pump
    except asyncio.CancelledError:
        pass
    log.info("Cerrando servicio")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API REST para control de accesos — tablet, configuración web, integración COCE (fase 2)",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción restringir al origen del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PanelApiAuthMiddleware)
app.add_middleware(TabletActorContextMiddleware)

# Rutas bajo /api (ver API_SPEC.md)
app.include_router(health.router, prefix=settings.api_prefix, tags=["Salud"])
app.include_router(coce_status.router, prefix=settings.api_prefix)
app.include_router(status.router, prefix=settings.api_prefix, tags=["Estado"])
app.include_router(modes.router, prefix=settings.api_prefix, tags=["Modos"])
app.include_router(events.router, prefix=settings.api_prefix, tags=["Eventos"])
app.include_router(config.router, prefix=settings.api_prefix, tags=["Configuración"])
app.include_router(panel.router, prefix=settings.api_prefix, tags=["Panel ETD8A12"])
app.include_router(panel_ws.router, prefix=f"{settings.api_prefix}/panel", tags=["Panel ETD8A12"])
app.include_router(auth_panel.router, prefix=settings.api_prefix)
app.include_router(tablet_v1.router, prefix=settings.api_prefix)
app.include_router(tablet_ws.router, prefix=f"{settings.api_prefix}/v1")
# Panphone / CSIP custom1 (módulo aparte, mismo prefijo /api)
app.include_router(csip_router, prefix=settings.api_prefix)
# Endpoints para integración ESP32 zaguán (sin prefijo /api, compat firmware)
app.include_router(zaguan_esp32_router)


# ─── Servir frontend en producción ─────────────────────────────────────────
# Si existe el build del frontend (frontend/dist o STATIC_DIR), se sirve la SPA:
# - /assets/* → archivos estáticos (JS, CSS)
# - Cualquier otra ruta que no sea /api, /docs, /redoc → index.html (SPA)
# Ver DESARROLLO.md, sección "Producción: servir el frontend desde el backend".

def _get_frontend_dist_path() -> Optional[Path]:
    if settings.static_dir:
        p = (BASE_DIR / settings.static_dir).resolve()
    else:
        p = BASE_DIR.parent / "frontend" / "dist"
    return p if p.is_dir() and (p / "index.html").exists() else None

_frontend_dist = _get_frontend_dist_path()

if _frontend_dist:
    _assets = _frontend_dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")
    log.info("Sirviendo frontend desde %s", _frontend_dist)

    @app.get("/")
    def serve_index():
        return FileResponse(str(_frontend_dist / "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """Cualquier ruta no cubierta por la API o /docs,/redoc devuelve la SPA."""
        return FileResponse(str(_frontend_dist / "index.html"))
else:
    @app.get("/")
    def root():
        """Raíz: info del servicio (cuando no se sirve frontend)."""
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "api": settings.api_prefix,
        }
