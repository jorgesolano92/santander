from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_username
from app.db import audit_store as audit
from app.db import branches_store as branches
from app.db import technicians_store as tech
from app.services.live_hub import live_hub

router = APIRouter(prefix="/technicians", tags=["Técnicos habilitados"])


async def _broadcast_technicians(items: list[dict]) -> dict:
    payload = {
        "type": "technicians_sync",
        "payload": {
            "technicians": items,
            "count": len(items),
        },
    }
    delivered = 0
    offline = 0
    for branch in branches.list_branches():
        bid = str(branch.get("id") or "")
        if not bid:
            continue
        ok = await live_hub.send_to_branch(bid, payload)
        if ok:
            delivered += 1
        else:
            offline += 1
    return {"delivered": delivered, "offline": offline}


@router.get("")
def list_all(_user: Annotated[str, Depends(get_current_username)]) -> dict:
    return {"technicians": tech.list_technicians()}


@router.post("/import")
async def import_csv(
    user: Annotated[str, Depends(get_current_username)],
    file: UploadFile = File(...),
) -> dict:
    name = (file.filename or "").lower()
    if not (name.endswith(".csv") or name.endswith(".txt")):
        raise HTTPException(
            status_code=400,
            detail="Sube un CSV (columnas: dni,nombre,apellidos,empresa,valido_hasta). Excel: exportar a CSV.",
        )
    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    rows = tech.parse_csv_text(text)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV vacío o sin columna dni")
    saved = tech.replace_all(rows)
    sync = await _broadcast_technicians(saved)
    audit.record_audit(
        actor_username=user,
        action="technicians.import",
        success=True,
        detail={"count": len(saved), **sync, "filename": file.filename},
    )
    return {"ok": True, "technicians": saved, "sync": sync}


@router.post("/sync-branches")
async def sync_branches(user: Annotated[str, Depends(get_current_username)]) -> dict:
    items = tech.list_technicians()
    sync = await _broadcast_technicians(items)
    audit.record_audit(
        actor_username=user,
        action="technicians.sync",
        success=True,
        detail={"count": len(items), **sync},
    )
    return {"ok": True, "sync": sync, "count": len(items)}
