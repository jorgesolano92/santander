"""Mensajes COCE → sucursal (relay exclusivo del backend del panel).

Flujo:
  COCE  --WS-->  backend panel (esta sucursal)
                    ├─ persiste siempre en BD local
                    ├─ si COCE_MESSAGE_SEND_WEB=true  → WS panel (/api/panel/ws/live)
                    └─ si COCE_MESSAGE_SEND_TABLET=true → WS tablets (/api/v1/ws/calls)

El COCE no habla con las tablets. Con SEND_WEB=false y SEND_TABLET=true
el mensaje no se emite al dashboard web, pero sí a las tablets por el hub del panel.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.db import coce_message_store
from app.db import technicians_store
from app.services import panel_live_hub, tablet_call_hub

log = logging.getLogger("coce.dispatcher")


def _handle_coce_message_sync(message: dict[str, Any]) -> None:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        payload = message
    message_id = str(payload.get("id") or "")
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not message_id or not title:
        log.warning("coce_message ignorado (falta id o title): %s", payload)
        return
    urgent = bool(payload.get("urgent"))
    sent_at = payload.get("sent_at")
    stored = coce_message_store.save_message(
        message_id=message_id,
        title=title,
        body=body,
        urgent=urgent,
        sent_at=str(sent_at) if sent_at else None,
        extra=payload,
    )

    delivered: list[str] = []
    # Tablets: mismo hub WS que modos en vivo y llamadas (tablet_call_hub).
    if settings.coce_message_send_tablet:
        n_tablets = tablet_call_hub.connected_client_count()
        tablet_call_hub.notify_coce_message(stored)
        delivered.append(f"tablet(ws={n_tablets})")
        if n_tablets == 0:
            log.warning(
                "Mensaje COCE id=%s: SEND_TABLET=true pero 0 tablets en /api/v1/ws/calls",
                message_id,
            )
    # Dashboard web: hub distinto (/api/panel/ws/live).
    if settings.coce_message_send_web:
        panel_live_hub.notify_coce_message(stored)
        delivered.append("web")

    log.info(
        "Mensaje COCE id=%s urgent=%s send_tablet=%s send_web=%s canales=%s",
        message_id,
        urgent,
        settings.coce_message_send_tablet,
        settings.coce_message_send_web,
        delivered or ["ninguno (ambos flags false)"],
    )


def _handle_technicians_sync_sync(message: dict[str, Any]) -> None:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    items = payload.get("technicians")
    if not isinstance(items, list):
        log.warning("technicians_sync sin lista")
        return
    count = technicians_store.replace_all(items)
    log.info("Técnicos sincronizados desde COCE: %s", count)


async def handle_coce_message(message: dict[str, Any]) -> None:
    msg_type = message.get("type")
    if msg_type == "coce_message":
        await asyncio.to_thread(_handle_coce_message_sync, message)
        return
    if msg_type == "technicians_sync":
        await asyncio.to_thread(_handle_technicians_sync_sync, message)
        return
    log.debug("Mensaje COCE→sucursal no manejado: %s", msg_type)
