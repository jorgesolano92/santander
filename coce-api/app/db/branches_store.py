from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.schema import ensure_schema
from app.db.session import get_connection
from app.services.secrets_crypto import decrypt_secret, encrypt_secret


def _new_ingest_token() -> str:
    return secrets.token_urlsafe(32)


def _row_to_public(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "host": row["host"],
        "port": int(row["port"]),
        "useHttps": bool(row["use_https"]),
        "usuarioTablet": row["tablet_user"],
        "hasPasswordTablet": bool(row["tablet_password_enc"]),
        "usuarioPanel": row["panel_user"] or None,
        "hasPasswordPanel": bool(row["panel_password_enc"]),
        "hasIngestToken": bool(row["ingest_token_enc"] if "ingest_token_enc" in row.keys() else False),
        "estado": row["estado"] or "operativo",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _row_to_internal(row: Any) -> dict[str, Any]:
    pub = _row_to_public(row)
    pub["passwordTablet"] = decrypt_secret(row["tablet_password_enc"])
    pub["passwordPanel"] = decrypt_secret(row["panel_password_enc"] or "")
    return pub


def list_branches() -> list[dict[str, Any]]:
    ensure_schema()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM branches ORDER BY nombre COLLATE NOCASE").fetchall()
        return [_row_to_public(r) for r in rows]


def get_branch(branch_id: str, *, internal: bool = False) -> Optional[dict[str, Any]]:
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
        if not row:
            return None
        return _row_to_internal(row) if internal else _row_to_public(row)


def create_branch(data: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Devuelve (sucursal pública, ingest_token en claro, solo al crear)."""
    ensure_schema()
    now = datetime.now(timezone.utc).isoformat()
    bid = data["id"]
    ingest_plain = _new_ingest_token()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO branches (
                id, nombre, host, port, use_https,
                tablet_user, tablet_password_enc,
                panel_user, panel_password_enc,
                ingest_token_enc,
                estado, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bid,
                data["nombre"],
                data["host"],
                int(data["port"]),
                1 if data.get("useHttps") else 0,
                data["usuarioTablet"],
                encrypt_secret(data["passwordTablet"]),
                (data.get("usuarioPanel") or "").strip() or None,
                encrypt_secret(data.get("passwordPanel") or ""),
                encrypt_secret(ingest_plain),
                data.get("estado") or "operativo",
                now,
                now,
            ),
        )
        conn.commit()
    out = get_branch(bid)
    assert out is not None
    return out, ingest_plain


def verify_ingest_token(branch_id: str, token: str) -> bool:
    if not token:
        return False
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ingest_token_enc FROM branches WHERE id = ?",
            (branch_id,),
        ).fetchone()
    if not row or not row["ingest_token_enc"]:
        return False
    try:
        return secrets.compare_digest(decrypt_secret(row["ingest_token_enc"]), token)
    except Exception:  # noqa: BLE001
        return False


def get_ingest_token(branch_id: str) -> Optional[str]:
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ingest_token_enc FROM branches WHERE id = ?",
            (branch_id,),
        ).fetchone()
    if not row or not row["ingest_token_enc"]:
        return None
    return decrypt_secret(row["ingest_token_enc"])


def update_branch(branch_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
    existing = get_branch(branch_id, internal=True)
    if not existing:
        return None
    now = datetime.now(timezone.utc).isoformat()
    tablet_pw = data.get("passwordTablet")
    if not tablet_pw:
        tablet_pw = existing["passwordTablet"]
    panel_pw = data.get("passwordPanel")
    if panel_pw is None or panel_pw == "":
        panel_pw = existing.get("passwordPanel") or ""
    panel_user = data.get("usuarioPanel")
    if panel_user is None:
        panel_user = existing.get("usuarioPanel")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE branches SET
                nombre = ?, host = ?, port = ?, use_https = ?,
                tablet_user = ?, tablet_password_enc = ?,
                panel_user = ?, panel_password_enc = ?,
                estado = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data.get("nombre", existing["nombre"]),
                data.get("host", existing["host"]),
                int(data.get("port", existing["port"])),
                1 if data.get("useHttps", existing["useHttps"]) else 0,
                data.get("usuarioTablet", existing["usuarioTablet"]),
                encrypt_secret(tablet_pw),
                (panel_user or "").strip() or None,
                encrypt_secret(panel_pw or ""),
                data.get("estado", existing.get("estado") or "operativo"),
                now,
                branch_id,
            ),
        )
        conn.commit()
    return get_branch(branch_id)


def delete_branch(branch_id: str) -> bool:
    ensure_schema()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM branches WHERE id = ?", (branch_id,))
        conn.commit()
        return cur.rowcount > 0
