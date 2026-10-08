"""HTTPS/WSS: rutas del certificado de servidor emitido por la CA propia."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import BASE_DIR, settings


def _resolve(path: Optional[str]) -> Optional[Path]:
    if not path or not path.strip():
        return None
    p = Path(path.strip())
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


def tls_files() -> Optional[tuple[Path, Path]]:
    """(cert, key) si están configurados y existen; None si no hay TLS."""
    cert = _resolve(settings.tls_cert_file)
    key = _resolve(settings.tls_key_file)
    if cert and key and cert.is_file() and key.is_file():
        return cert, key
    return None
