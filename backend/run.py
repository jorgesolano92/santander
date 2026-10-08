"""
Punto de arranque del backend.

Sin certificado: HTTP en HTTP_PORT (8000), con recarga en caliente (BACKEND_RELOAD=0 para desactivarla).
Con TLS_CERT_FILE/TLS_KEY_FILE: mismo proceso sirve HTTP (ESP32, compatibilidad) y HTTPS/WSS en
HTTPS_PORT (8443, tablets). Un solo proceso para que tablets y panel compartan el estado en memoria.
"""
import asyncio
import os

import uvicorn

from app.core.config import settings
from app.core.tls import tls_files


async def _serve_http_and_https(cert: str, key: str) -> None:
    from app.main import app

    http = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=settings.http_port))
    # El lifespan (tareas de fondo, Modbus, COCE) solo debe arrancar una vez.
    https = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=settings.https_port,
            ssl_certfile=cert,
            ssl_keyfile=key,
            lifespan="off",
        )
    )
    await asyncio.gather(http.serve(), https.serve())


if __name__ == "__main__":
    files = tls_files()
    if files:
        print(f"HTTP :{settings.http_port}  ·  HTTPS/WSS :{settings.https_port} ({files[0]})")
        asyncio.run(_serve_http_and_https(str(files[0]), str(files[1])))
    else:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=settings.http_port,
            reload=os.getenv("BACKEND_RELOAD", "1") != "0",
        )
