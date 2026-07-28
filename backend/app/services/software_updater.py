"""Descarga y aplicación de updates publicados por el COCE."""
from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse, urlunparse

from app.core.config import settings
from app.coce.notify import emit_coce_event
from app.db import software_update_store as store

log = logging.getLogger("software.updater")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent

_CHUNK_SIZE = 256 * 1024

_EXCLUDE_DIR_NAMES = {
    "data",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
}
_EXCLUDE_FILE_NAMES = {".env", ".env.local"}
_EXCLUDE_SUFFIXES = {".db", ".db-journal", ".sqlite", ".sqlite3"}


def coce_http_base() -> str:
    raw = (settings.coce_ws_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = "https" if parsed.scheme in ("wss", "https") else "http"
    netloc = parsed.netloc
    if not netloc:
        return ""
    # ws URL suele ser .../api/coce/ws/branch/<id> → base http://host:port
    return urlunparse((scheme, netloc, "", "", "", ""))


def _should_skip_member(name: str) -> bool:
    parts = Path(name).parts
    for part in parts:
        if part in _EXCLUDE_DIR_NAMES:
            return True
    base = Path(name).name
    if base in _EXCLUDE_FILE_NAMES or base.startswith(".env."):
        return True
    if Path(name).suffix.lower() in _EXCLUDE_SUFFIXES:
        return True
    return False


def _report(release_id: str, status: str, version: str, error: Optional[str] = None) -> None:
    emit_coce_event(
        "update_status",
        {
            "release_id": release_id,
            "status": status,
            "version": version,
            "error": error,
        },
    )


def download_artifact(pending: dict[str, Any], dest: Path) -> Path:
    base = coce_http_base()
    if not base:
        raise RuntimeError("COCE_WS_URL no configurada; no se puede descargar el artefacto")
    path = str(pending.get("download_path") or "")
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    req = urlrequest.Request(
        url,
        headers={
            "X-Coce-Ingest-Token": settings.coce_ingest_token or "",
            "X-Coce-Installation-Id": settings.coce_installation_id or "",
        },
        method="GET",
    )
    hasher = hashlib.sha256()
    expected = str(pending.get("sha256") or "").strip().lower()
    try:
        with urlrequest.urlopen(req, timeout=600) as resp:
            with dest.open("wb") as out:
                while True:
                    chunk = resp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    out.write(chunk)
    except urlerror.HTTPError as exc:
        raise RuntimeError(f"Descarga COCE falló HTTP {exc.code}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Descarga COCE falló: {exc.reason}") from exc
    if expected:
        digest = hasher.hexdigest()
        if digest != expected:
            raise RuntimeError(f"SHA256 no coincide (esperado {expected}, got {digest})")
    return dest


def iter_artifact_chunks(
    pending: dict[str, Any],
    *,
    chunk_size: int = _CHUNK_SIZE,
):
    """Transmite el artefacto del COCE en trozos (sin cargarlo entero en RAM)."""
    base = coce_http_base()
    if not base:
        raise RuntimeError("COCE_WS_URL no configurada; no se puede descargar el artefacto")
    path = str(pending.get("download_path") or "")
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    req = urlrequest.Request(
        url,
        headers={
            "X-Coce-Ingest-Token": settings.coce_ingest_token or "",
            "X-Coce-Installation-Id": settings.coce_installation_id or "",
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=600) as resp:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    except urlerror.HTTPError as exc:
        raise RuntimeError(f"Descarga COCE falló HTTP {exc.code}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Descarga COCE falló: {exc.reason}") from exc


def stream_apk_download(pending: dict[str, Any]):
    """Generador para StreamingResponse al descargar APK en el navegador."""
    release_id = str(pending.get("release_id") or "")
    version = str(pending.get("version") or "")
    expected = str(pending.get("sha256") or "").strip().lower()
    _report(release_id, "downloading", version)
    hasher = hashlib.sha256()
    try:
        for chunk in iter_artifact_chunks(pending):
            hasher.update(chunk)
            yield chunk
        if expected:
            digest = hasher.hexdigest()
            if digest != expected:
                msg = f"SHA256 no coincide (esperado {expected}, got {digest})"
                _report(release_id, "failed", version, msg)
                raise RuntimeError(msg)
        store.mark_apk_seen(version, str(pending.get("published_at") or "") or None)
        _report(release_id, "success", version)
    except Exception as exc:
        if "SHA256 no coincide" not in str(exc):
            _report(release_id, "failed", version, str(exc))
        raise


def apply_panel_update(pending: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    state = store.get_state()
    pending = pending or state.get("pending")
    if not pending or pending.get("kind") != "panel":
        raise RuntimeError("No hay actualización de panel pendiente")
    release_id = str(pending.get("release_id") or "")
    version = str(pending.get("version") or "")
    _report(release_id, "downloading", version)
    tmp = Path(tempfile.mkdtemp(prefix="panel-update-"))
    try:
        zip_path = tmp / "panel.zip"
        download_artifact(pending, zip_path)
        _report(release_id, "applying", version)
        extract_dir = tmp / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir() or _should_skip_member(info.filename):
                    continue
                zf.extract(info, extract_dir)

        # Copiar backend/app (código) sin tocar backend/data
        src_backend = extract_dir / "backend"
        if src_backend.is_dir():
            for src in src_backend.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(src_backend)
                if _should_skip_member(str(rel)):
                    continue
                # no sobrescribir data/
                if rel.parts and rel.parts[0] == "data":
                    continue
                dest = _BACKEND_ROOT / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

        # Frontend dist → repo frontend/dist o backend/../frontend/dist
        src_fe = extract_dir / "frontend" / "dist"
        if not src_fe.is_dir():
            src_fe = extract_dir / "frontend"
        if src_fe.is_dir():
            dest_fe = _REPO_ROOT / "frontend" / "dist"
            if dest_fe.exists():
                shutil.rmtree(dest_fe)
            dest_fe.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_fe, dest_fe)

        store.mark_panel_applied(version)
        _report(release_id, "success", version)
        log.info("Panel update aplicada version=%s", version)
        return {"ok": True, "version": version, "restart_required": True}
    except Exception as exc:  # noqa: BLE001
        _report(release_id, "failed", version, str(exc))
        log.exception("Error aplicando update panel")
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download_apk_to_path(dest: Path, pending: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    state = store.get_state()
    pending = pending or state.get("pending")
    if not pending or pending.get("kind") != "tablet_apk":
        raise RuntimeError("No hay APK pendiente")
    release_id = str(pending.get("release_id") or "")
    version = str(pending.get("version") or "")
    _report(release_id, "downloading", version)
    download_artifact(pending, dest)
    store.mark_apk_seen(version, str(pending.get("published_at") or "") or None)
    _report(release_id, "success", version)
    return {"ok": True, "version": version, "path": str(dest)}
