from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from app.db.schema import ensure_schema
from app.db.session import get_connection

Role = Literal["admin", "operador"]
VALID_ROLES = frozenset({"admin", "operador"})


def _normalize_role(role: Optional[str]) -> str:
    r = (role or "operador").strip().lower()
    return r if r in VALID_ROLES else "operador"


def count_users() -> int:
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM coce_users").fetchone()
        return int(row[0]) if row else 0


def get_user_by_username(username: str) -> Optional[tuple[int, str, str, str]]:
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM coce_users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        if not row:
            return None
        role = row["role"] if "role" in row.keys() else "operador"
        return int(row["id"]), str(row["username"]), str(row["password_hash"]), _normalize_role(role)


def get_user_by_id(user_id: int) -> Optional[tuple[int, str, str, str]]:
    ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM coce_users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        role = row["role"] if "role" in row.keys() else "operador"
        return int(row["id"]), str(row["username"]), str(row["password_hash"]), _normalize_role(role)


def create_user(username: str, password_hash: str, role: str = "operador") -> int:
    ensure_schema()
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO coce_users (username, password_hash, created_at, role)
            VALUES (?, ?, ?, ?)
            """,
            (username.strip(), password_hash, now, _normalize_role(role)),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_users() -> list[dict[str, Any]]:
    ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, created_at, role FROM coce_users ORDER BY username ASC"
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        role = row["role"] if "role" in row.keys() else "operador"
        out.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "createdAt": row["created_at"],
                "role": _normalize_role(role),
            }
        )
    return out


def update_user(
    user_id: int,
    *,
    role: Optional[str] = None,
    password_hash: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    ensure_schema()
    existing = get_user_by_id(user_id)
    if not existing:
        return None
    with get_connection() as conn:
        if role is not None:
            conn.execute(
                "UPDATE coce_users SET role = ? WHERE id = ?",
                (_normalize_role(role), user_id),
            )
        if password_hash is not None:
            conn.execute(
                "UPDATE coce_users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )
        conn.commit()
    updated = get_user_by_id(user_id)
    if not updated:
        return None
    return {
        "id": updated[0],
        "username": updated[1],
        "role": updated[3],
    }


def delete_user(user_id: int) -> bool:
    ensure_schema()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM coce_users WHERE id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0
