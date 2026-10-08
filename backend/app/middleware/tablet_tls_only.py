"""Con TABLET_REQUIRE_TLS=true, la API de tablets (/api/v1, también el WS) solo por HTTPS/WSS."""
from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings


class TabletTlsOnlyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.prefix = f"{settings.api_prefix}/v1"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            settings.tablet_require_tls
            and scope["type"] in ("http", "websocket")
            and str(scope.get("path", "")).startswith(self.prefix)
            and scope.get("scheme") not in ("https", "wss")
        ):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            body = b'{"detail":"La API de tablets requiere HTTPS"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
