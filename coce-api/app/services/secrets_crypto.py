"""Cifrado de credenciales de sucursal en reposo (Fernet)."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_fernet: Fernet | None = None


def _fernet_key_bytes() -> bytes:
    raw = (settings.secrets_key or "").strip()
    if raw:
        return raw.encode("utf-8")
    digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_fernet_key_bytes())
    return _fernet


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    return _get_fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(cipher: str) -> str:
    if not cipher:
        return ""
    try:
        return _get_fernet().decrypt(cipher.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("No se pudo descifrar el secreto (clave COCE_SECRETS_KEY incorrecta)") from e
