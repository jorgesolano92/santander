"""COCE API — servidor central FastAPI."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.schema import ensure_schema
from app.api.routes import auth, branches, branch_ops, audit, ws, messages, technicians, updates
from app.services.live_hub import live_hub


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    sweep_task = asyncio.create_task(live_hub.status_sweep_loop())
    yield
    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

_cors_kw: dict = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.cors_allow_all:
    _cors_kw["allow_origin_regex"] = r"https?://.*"
else:
    _cors_kw["allow_origins"] = settings.cors_origin_list
app.add_middleware(CORSMiddleware, **_cors_kw)

prefix = settings.api_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(branches.router, prefix=prefix)
app.include_router(branch_ops.router, prefix=prefix)
app.include_router(audit.router, prefix=prefix)
app.include_router(messages.router, prefix=prefix)
app.include_router(technicians.router, prefix=prefix)
app.include_router(updates.router, prefix=prefix)
app.include_router(ws.router, prefix=prefix)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "coce-api"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
