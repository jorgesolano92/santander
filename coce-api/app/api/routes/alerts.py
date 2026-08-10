from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_username
from app.db import alerts_store as alerts

router = APIRouter(prefix="/alerts", tags=["Alertas COCE"])


@router.get("")
def list_alerts(
    _user: Annotated[str, Depends(get_current_username)],
    limit: int = Query(default=100, ge=1, le=500),
    active: Optional[bool] = None,
    branch_id: Optional[str] = None,
) -> dict:
    items = alerts.list_alerts(limit=limit, active=active, branch_id=branch_id)
    return {"alerts": items, "limit": limit}
