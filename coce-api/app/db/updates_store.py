"""Releases de software (panel zip / APK) y despliegues a sucursales."""
from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.db.session import get_connection

_ROOT = Path(__file__).resolve().parent.parent.parent


def releases_dir() -> Path:
    path = _ROOT / "data" / "releases"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_release(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "version": row["version"],
        "changelog": row["changelog"] or "",
        "sha256": row["sha256"],
        "originalFilename": row["original_filename"] or "",
        "source": row["source"] or "upload",
        "createdAt": row["created_at"],
        "createdBy": row["created_by"] or "",
        "downloadPath": f"/api/coce/updates/releases/{row['id']}/artifact",
    }


def _row_deployment(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "releaseId": row["release_id"],
        "branchId": row["branch_id"],
        "branchNombre": row["branch_nombre"] or "",
        "status": row["status"],
        "error": row["error"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "version": row["version"] if "version" in row.keys() else None,
        "kind": row["kind"] if "kind" in row.keys() else None,
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_release_from_upload(
    *,
    kind: str,
    version: str,
    changelog: str,
    created_by: str,
    source: str,
    original_filename: str,
    file_bytes: bytes,
) -> dict[str, Any]:
    release_id = str(uuid.uuid4())
    safe_kind = "apk" if kind == "tablet_apk" else "panel"
    ext = Path(original_filename).suffix or (".apk" if safe_kind == "apk" else ".zip")
    rel_name = f"{safe_kind}/{release_id}{ext}"
    dest = releases_dir() / rel_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file_bytes)
    digest = sha256_file(dest)
    created = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO software_releases (
                id, kind, version, changelog, sha256, storage_path,
                original_filename, source, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                release_id,
                kind,
                version.strip(),
                (changelog or "").strip(),
                digest,
                rel_name.replace("\\", "/"),
                original_filename,
                source,
                created,
                created_by,
            ),
        )
        conn.commit()
    return get_release(release_id)  # type: ignore[return-value]


def create_release_from_path(
    *,
    kind: str,
    version: str,
    changelog: str,
    created_by: str,
    source: str,
    source_file: Path,
    original_filename: str,
) -> dict[str, Any]:
    release_id = str(uuid.uuid4())
    safe_kind = "apk" if kind == "tablet_apk" else "panel"
    ext = source_file.suffix or ".zip"
    rel_name = f"{safe_kind}/{release_id}{ext}"
    dest = releases_dir() / rel_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, dest)
    digest = sha256_file(dest)
    created = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO software_releases (
                id, kind, version, changelog, sha256, storage_path,
                original_filename, source, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                release_id,
                kind,
                version.strip(),
                (changelog or "").strip(),
                digest,
                rel_name.replace("\\", "/"),
                original_filename,
                source,
                created,
                created_by,
            ),
        )
        conn.commit()
    return get_release(release_id)  # type: ignore[return-value]


def get_release(release_id: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM software_releases WHERE id = ?",
            (release_id,),
        ).fetchone()
    return _row_release(row) if row else None


def get_release_storage_path(release_id: str) -> Optional[Path]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT storage_path FROM software_releases WHERE id = ?",
            (release_id,),
        ).fetchone()
    if not row:
        return None
    path = releases_dir() / str(row["storage_path"])
    return path if path.is_file() else None


def list_releases(*, kind: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with get_connection() as conn:
        if kind:
            rows = conn.execute(
                """
                SELECT * FROM software_releases
                WHERE kind = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (kind, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM software_releases
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [_row_release(r) for r in rows]


def create_deployments(
    *,
    release_id: str,
    targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    now = _now()
    created: list[dict[str, Any]] = []
    with get_connection() as conn:
        for branch in targets:
            dep_id = str(uuid.uuid4())
            branch_id = str(branch.get("id") or "")
            branch_nombre = str(branch.get("nombre") or branch_id)
            conn.execute(
                """
                INSERT INTO software_deployments (
                    id, release_id, branch_id, branch_nombre, status, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
                """,
                (dep_id, release_id, branch_id, branch_nombre, now, now),
            )
            created.append(
                {
                    "id": dep_id,
                    "releaseId": release_id,
                    "branchId": branch_id,
                    "branchNombre": branch_nombre,
                    "status": "pending",
                    "error": None,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
        conn.commit()
    return created


def update_deployment_status(
    *,
    release_id: str,
    branch_id: str,
    status: str,
    error: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    now = _now()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM software_deployments
            WHERE release_id = ? AND branch_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (release_id, branch_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE software_deployments
            SET status = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error, now, row["id"]),
        )
        conn.commit()
        full = conn.execute(
            """
            SELECT d.*, r.version, r.kind
            FROM software_deployments d
            JOIN software_releases r ON r.id = d.release_id
            WHERE d.id = ?
            """,
            (row["id"],),
        ).fetchone()
    return _row_deployment(full) if full else None


def list_deployments(*, limit: int = 100, release_id: Optional[str] = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with get_connection() as conn:
        if release_id:
            rows = conn.execute(
                """
                SELECT d.*, r.version, r.kind
                FROM software_deployments d
                JOIN software_releases r ON r.id = d.release_id
                WHERE d.release_id = ?
                ORDER BY d.updated_at DESC
                LIMIT ?
                """,
                (release_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT d.*, r.version, r.kind
                FROM software_deployments d
                JOIN software_releases r ON r.id = d.release_id
                ORDER BY d.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [_row_deployment(r) for r in rows]


def panel_source_dir() -> Optional[Path]:
    raw = (settings.panel_source_dir or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None
