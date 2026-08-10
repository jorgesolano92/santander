from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_client_ip, get_current_username, require_admin
from app.db import audit_store as audit
from app.db import branches_store as branches
from app.db import messages_store as messages
from app.services.live_hub import live_hub

router = APIRouter(prefix="/messages", tags=["Mensajería COCE"])


class SendMessageBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    urgent: bool = False
    branchIds: list[str] = Field(default_factory=list)
    sendToAll: bool = False


@router.post("/send")
async def send_message(
    body: SendMessageBody,
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
) -> dict:
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

    sent: list[dict] = []
    for branch in targets:
        branch_id = str(branch.get("id") or "")
        branch_nombre = str(branch.get("nombre") or branch_id)
        row = messages.insert_message(
            actor_username=user,
            title=body.title,
            body=body.body,
            urgent=body.urgent,
            branch_id=branch_id,
            branch_nombre=branch_nombre,
            delivery_status="pending",
        )
        payload = {
            "type": "coce_message",
            "payload": {
                "id": row["id"],
                "title": row["title"],
                "body": row["body"],
                "urgent": row["urgent"],
                "sent_at": row["createdAt"],
            },
        }
        delivered = await live_hub.send_to_branch(branch_id, payload)
        status = "delivered" if delivered else "offline"
        messages.update_delivery(row["id"], status)
        row["deliveryStatus"] = status
        sent.append(row)

    audit.record_audit(
        actor_username=user,
        action="message.send",
        success=True,
        detail={
            "count": len(sent),
            "urgent": body.urgent,
            "title": body.title,
            "branch_ids": [r["branchId"] for r in sent],
        },
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "messages": sent}


@router.get("")
def list_sent_messages(
    _user: Annotated[str, Depends(get_current_username)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    branch_id: Optional[str] = None,
    urgent: Optional[bool] = None,
    delivery_status: Optional[
        Literal["pending", "delivered", "offline", "read"]
    ] = None,
    from_ts: Optional[str] = Query(default=None, alias="from"),
    to_ts: Optional[str] = Query(default=None, alias="to"),
    q: Optional[str] = None,
) -> dict:
    items = messages.list_messages(
        limit=limit,
        offset=offset,
        branch_id=branch_id,
        urgent=urgent,
        delivery_status=delivery_status,
        from_ts=from_ts,
        to_ts=to_ts,
        q=q,
    )
    return {"messages": items, "limit": limit, "offset": offset}


class AckMessageBody(BaseModel):
    readBy: str = Field(default="branch", max_length=64)
    readAt: Optional[str] = None


@router.post("/{message_id}/ack")
def ack_message(
    message_id: str,
    body: AckMessageBody,
    request: Request,
    user: Annotated[str, Depends(get_current_username)],
) -> dict:
    row = messages.mark_read(
        message_id,
        read_by=body.readBy or user,
        read_at=body.readAt,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    audit.record_audit(
        actor_username=user,
        action="message.ack",
        success=True,
        detail={"message_id": message_id, "read_by": row.get("readBy")},
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "message": row}


@router.delete("/{message_id}")
def delete_message(
    message_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> dict:
    existing = messages.get_message(message_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    ok = messages.delete_message(message_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    audit.record_audit(
        actor_username=user.username,
        action="message.delete",
        success=True,
        detail={
            "message_id": message_id,
            "title": existing.get("title"),
            "branch_id": existing.get("branchId"),
        },
        ip_address=get_client_ip(request),
    )
    return {"ok": True, "id": message_id}
