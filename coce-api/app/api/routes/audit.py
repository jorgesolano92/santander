from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_username
from app.db import audit_store as audit

router = APIRouter(prefix="/audit", tags=["Auditoría"])


@router.get("")
def list_logs(
    _user: Annotated[str, Depends(get_current_username)],
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    branch_id: Optional[str] = None,
    action: Optional[str] = None,
    from_ts: Optional[str] = Query(default=None, alias="from"),
    to_ts: Optional[str] = Query(default=None, alias="to"),
) -> dict:
    logs = audit.list_audit(
        limit=limit,
        offset=offset,
        branch_id=branch_id,
        action=action,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return {"logs": logs, "limit": limit, "offset": offset}
