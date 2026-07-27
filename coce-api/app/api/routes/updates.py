"""API actualizaciones remotas (releases panel/APK + despliegue a sucursales)."""
from __future__ import annotations

import logging
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_client_ip, get_current_username
from app.core.config import settings
from app.db import audit_store as audit
from app.db import branches_store as branches
from app.db import updates_store as updates
from app.services.live_hub import live_hub
from app.services.jwt_service import decode_token
from app.services.panel_packager import build_panel_zip

log = logging.getLogger("coce.updates")
router = APIRouter(prefix="/updates", tags=["Actualizaciones remotas"])

KindLiteral = Literal["panel", "tablet_apk"]


class DeployBody(BaseModel):
    releaseId: str = Field(min_length=1)
    branchIds: list[str] = Field(default_factory=list)
    sendToAll: bool = False


class FromLocalBody(BaseModel):
    version: Optional[str] = None
    changelog: str = ""


def _authorize_artifact(
    release_id: str,
    authorization: Optional[str],
    x_coce_ingest_token: Optional[str],
    x_coce_installation_id: Optional[str],
) -> None:
    """Dashboard JWT o token de ingest de sucursal."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            if payload.get("sub"):
                return
        except ValueError:
            pass
    if x_coce_ingest_token and x_coce_installation_id:
        if branches.verify_ingest_token(x_coce_installation_id, x_coce_ingest_token):
            return
        raise HTTPException(status_code=403, detail="Token de sucursal inválido")
    raise HTTPException(status_code=401, detail="No autorizado")


@router.get("/releases")
def list_releases(
    _user: Annotated[str, Depends(get_current_username)],
    kind: Optional[KindLiteral] = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    return {"releases": updates.list_releases(kind=kind, limit=limit)}


@router.post("/releases")
async def upload_release(
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
    kind: Annotated[KindLiteral, Form()],
    version: Annotated[str, Form()],
    file: UploadFile = File(...),
    changelog: Annotated[str, Form()] = "",
) -> dict:
    version = (version or "").strip()
    if not version:
        raise HTTPException(status_code=400, detail="version es obligatoria")
    filename = file.filename or "artifact.bin"
    lower = filename.lower()
    if kind == "tablet_apk" and not lower.endswith(".apk"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .apk")
    if kind == "panel" and not (lower.endswith(".zip") or lower.endswith(".apk")):
        # panel normalmente zip; permitimos zip
        if not lower.endswith(".zip"):
            raise HTTPException(status_code=400, detail="El paquete panel debe ser .zip")

    raw = await file.read()
    max_bytes = max(1, int(settings.updates_max_upload_mb)) * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Archivo demasiado grande (máx {settings.updates_max_upload_mb} MB)",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    release = updates.create_release_from_upload(
        kind=kind,
        version=version,
        changelog=changelog or "",
        created_by=user,
        source="upload",
        original_filename=filename,
        file_bytes=raw,
    )
    audit.record_audit(
        actor_username=user,
        action="updates.release_upload",
        success=True,
        detail={"release_id": release["id"], "kind": kind, "version": version},
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "release": release}


@router.post("/releases/from-local")
def publish_from_local(
    body: FromLocalBody,
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
) -> dict:
    source = updates.panel_source_dir()
    if source is None:
        raise HTTPException(
            status_code=400,
            detail="Configura COCE_PANEL_SOURCE_DIR apuntando al checkout del panel",
        )
    try:
        zip_path, auto_version = build_panel_zip(source)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    version = (body.version or "").strip() or auto_version
    try:
        release = updates.create_release_from_path(
            kind="panel",
            version=version,
            changelog=body.changelog or "",
            created_by=user,
            source="local",
            source_file=zip_path,
            original_filename=zip_path.name,
        )
    finally:
        try:
            zip_path.unlink(missing_ok=True)
            zip_path.parent.rmdir()
        except OSError:
            pass
    audit.record_audit(
        actor_username=user,
        action="updates.release_from_local",
        success=True,
        detail={"release_id": release["id"], "version": version, "source_dir": str(source)},
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "release": release}


@router.get("/releases/{release_id}/artifact")
def download_artifact(
    release_id: str,
    authorization: Annotated[Optional[str], Header()] = None,
    x_coce_ingest_token: Annotated[Optional[str], Header()] = None,
    x_coce_installation_id: Annotated[Optional[str], Header()] = None,
) -> FileResponse:
    _authorize_artifact(
        release_id,
        authorization,
        x_coce_ingest_token,
        x_coce_installation_id,
    )
    release = updates.get_release(release_id)
    path = updates.get_release_storage_path(release_id)
    if not release or not path:
        raise HTTPException(status_code=404, detail="Release no encontrado")
    media = (
        "application/vnd.android.package-archive"
        if release["kind"] == "tablet_apk"
        else "application/zip"
    )
    filename = release.get("originalFilename") or path.name
    return FileResponse(path, media_type=media, filename=filename)


@router.post("/deploy")
async def deploy_release(
    body: DeployBody,
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
) -> dict:
    release = updates.get_release(body.releaseId)
    if not release:
        raise HTTPException(status_code=404, detail="Release no encontrado")
    if not body.sendToAll and not body.branchIds:
        raise HTTPException(
            status_code=400,
            detail="Selecciona al menos una sucursal o envía a todas",
        )
    all_branches = branches.list_branches()
    if body.sendToAll:
        targets = all_branches
    else:
        wanted = {bid.strip() for bid in body.branchIds if bid.strip()}
        targets = [b for b in all_branches if b.get("id") in wanted]
        if not targets:
            raise HTTPException(status_code=404, detail="Ninguna sucursal válida")

    deployments = updates.create_deployments(release_id=release["id"], targets=targets)
    results: list[dict] = []
    for dep in deployments:
        payload = {
            "type": "software_update",
            "payload": {
                "release_id": release["id"],
                "version": release["version"],
                "kind": release["kind"],
                "download_path": release["downloadPath"],
                "sha256": release["sha256"],
                "published_at": release["createdAt"],
                "changelog": release.get("changelog") or "",
                "mandatory": False,
                "deployment_id": dep["id"],
            },
        }
        delivered = await live_hub.send_to_branch(dep["branchId"], payload)
        status = "available" if delivered else "offline"
        updates.update_deployment_status(
            release_id=release["id"],
            branch_id=dep["branchId"],
            status=status,
            error=None if delivered else "Sucursal offline (WS)",
        )
        results.append({**dep, "status": status, "delivered": delivered})

    audit.record_audit(
        actor_username=user,
        action="updates.deploy",
        success=True,
        detail={
            "release_id": release["id"],
            "kind": release["kind"],
            "version": release["version"],
            "count": len(results),
        },
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "release": release, "deployments": results}


@router.get("/deployments")
def list_deployments(
    _user: Annotated[str, Depends(get_current_username)],
    release_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    return {"deployments": updates.list_deployments(limit=limit, release_id=release_id)}
