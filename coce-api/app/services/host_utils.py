"""Normalización y validación de host/IP de sucursal."""
from __future__ import annotations

import ipaddress
import re

_HOSTNAME_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$"
)
_IPV4_LIKE_RE = re.compile(r"^[\d.]+$")


def normalize_host(raw: str) -> str:
    """Quita protocolo, rutas y :puerto si el usuario los pegó en el campo host."""
    s = (raw or "").strip()
    for prefix in ("https://", "http://"):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :]
    s = s.split("/")[0].strip()
    if s.startswith("[") and "]" in s:
        return s[: s.index("]") + 1]
    if ":" in s:
        host_part, _, port_part = s.rpartition(":")
        if port_part.isdigit():
            s = host_part
    return s.strip()


def validate_host(host: str) -> None:
    if not host:
        raise ValueError("Indica la IP o hostname del PC de la sucursal.")
    if host.lower() == "localhost":
        return

    if _IPV4_LIKE_RE.match(host):
        try:
            addr = ipaddress.ip_address(host)
        except ValueError as e:
            raise ValueError(
                f"IPv4 no válida: «{host}». "
                "Debe tener cuatro números (ej. 192.168.1.155), no algo como 192.168.1.1.155."
            ) from e
        if not isinstance(addr, ipaddress.IPv4Address):
            raise ValueError(f"Se esperaba IPv4, no «{host}».")
        return

    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass

    if len(host) <= 253 and _HOSTNAME_RE.match(host):
        return

    raise ValueError(
        f"Host no válido: «{host}». "
        "Usa una IPv4 (ej. 192.168.1.50), localhost o un nombre DNS; sin http:// ni :puerto."
    )
