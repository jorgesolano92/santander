"""Técnicos habilitados sincronizados desde COCE."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.session import get_connection


def _init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS technicians (
            dni TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            apellidos TEXT NOT NULL DEFAULT '',
            empresa TEXT NOT NULL DEFAULT '',
            valido_hasta TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def replace_all(items: list[dict[str, Any]]) -> int:
    _init_db()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute("DELETE FROM technicians")
    count = 0
    for item in items:
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
        count += 1
    conn.commit()
    conn.close()
    return count


def find_by_dni(dni: str) -> Optional[dict[str, Any]]:
    _init_db()
    key = dni.strip().upper()
    conn = get_connection()
    row = conn.execute(
        """
        SELECT dni, nombre, apellidos, empresa, valido_hasta, active, updated_at
        FROM technicians WHERE UPPER(dni) = ?
        """,
        (key,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "dni": row[0],
        "nombre": row[1],
        "apellidos": row[2],
        "empresa": row[3],
        "valido_hasta": row[4],
        "active": bool(row[5]),
        "updated_at": row[6],
    }


def list_all() -> list[dict[str, Any]]:
    _init_db()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT dni, nombre, apellidos, empresa, valido_hasta, active, updated_at
        FROM technicians ORDER BY apellidos, nombre
        """
    ).fetchall()
    conn.close()
    return [
        {
            "dni": r[0],
            "nombre": r[1],
            "apellidos": r[2],
            "empresa": r[3],
            "valido_hasta": r[4],
            "active": bool(r[5]),
            "updated_at": r[6],
        }
        for r in rows
    ]
