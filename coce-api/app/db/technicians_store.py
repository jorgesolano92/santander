from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.schema import ensure_schema
from app.db.session import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_technicians(*, active_only: bool = False) -> list[dict[str, Any]]:
    ensure_schema()
    with get_connection() as conn:
        if active_only:
            rows = conn.execute(
                """
                SELECT dni, nombre, apellidos, empresa, valido_hasta, active, updated_at
                FROM technicians WHERE active = 1
                ORDER BY apellidos, nombre
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT dni, nombre, apellidos, empresa, valido_hasta, active, updated_at
                FROM technicians
                ORDER BY apellidos, nombre
                """
            ).fetchall()
    return [_row(r) for r in rows]


def replace_all(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ensure_schema()
    now = _now()
    with get_connection() as conn:
        conn.execute("DELETE FROM technicians")
        for item in rows:
            dni = str(item.get("dni") or "").strip().upper()
            if not dni:
                continue
            conn.execute(
                """
                INSERT INTO technicians (
                    dni, nombre, apellidos, empresa, valido_hasta, active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dni,
                    str(item.get("nombre") or "").strip(),
                    str(item.get("apellidos") or "").strip(),
                    str(item.get("empresa") or "").strip(),
                    (str(item.get("valido_hasta") or "").strip() or None),
                    1 if item.get("active", True) else 0,
                    now,
                ),
            )
        conn.commit()
    return list_technicians()


def parse_csv_text(raw: str) -> list[dict[str, Any]]:
    text = raw.lstrip("\ufeff").strip()
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict[str, Any]] = []
    for row in reader:
        if not row:
            continue
        # Normalize headers
        mapped = {str(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        dni = mapped.get("dni") or mapped.get("nif") or mapped.get("documento") or ""
        if not dni:
            continue
        out.append(
            {
                "dni": dni,
                "nombre": mapped.get("nombre") or mapped.get("name") or "",
                "apellidos": mapped.get("apellidos")
                or mapped.get("apellido")
                or mapped.get("surname")
                or "",
                "empresa": mapped.get("empresa") or mapped.get("company") or "",
                "valido_hasta": mapped.get("valido_hasta")
                or mapped.get("validez")
                or mapped.get("valid_until")
                or "",
                "active": True,
            }
        )
    return out


def _row(row: tuple) -> dict[str, Any]:
    dni, nombre, apellidos, empresa, valido_hasta, active, updated_at = row
    return {
        "dni": dni,
        "nombre": nombre,
        "apellidos": apellidos,
        "empresa": empresa,
        "valido_hasta": valido_hasta,
        "active": bool(active),
        "updated_at": updated_at,
    }
