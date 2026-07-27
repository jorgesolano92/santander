"""Empaquetado local del panel sucursal (backend + frontend/dist)."""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

_EXCLUDE_DIR_NAMES = {
    "data",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
_EXCLUDE_FILE_SUFFIXES = {".db", ".db-journal", ".sqlite", ".sqlite3"}
_EXCLUDE_FILE_NAMES = {".env", ".env.local"}


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    for part in rel.parts:
        if part in _EXCLUDE_DIR_NAMES:
            return True
    if path.name in _EXCLUDE_FILE_NAMES:
        return True
    if path.suffix.lower() in _EXCLUDE_FILE_SUFFIXES:
        return True
    if path.name.startswith(".env."):
        return True
    return False


def _iter_files(src: Path) -> Iterable[Path]:
    for p in src.rglob("*"):
        if p.is_file() and not _should_skip(p, src):
            yield p


def build_panel_zip(source_dir: Path) -> tuple[Path, str]:
    """
    Crea un zip temporal con backend/ y frontend/dist (o frontend/ si no hay dist).
    Devuelve (path_zip, version_sugerida).
    """
    backend = source_dir / "backend"
    frontend = source_dir / "frontend"
    if not backend.is_dir():
        raise FileNotFoundError(f"No se encontró backend/ en {source_dir}")

    dist = frontend / "dist"
    frontend_payload = dist if dist.is_dir() else (frontend if frontend.is_dir() else None)
    if frontend_payload is None:
        raise FileNotFoundError(f"No se encontró frontend/dist ni frontend/ en {source_dir}")

    version = datetime.now(timezone.utc).strftime("%Y.%m.%d-%H%M")
    git_head = source_dir / ".git" / "HEAD"
    # short hint only; no git subprocess required
    if (source_dir / ".git").exists():
        try:
            head = (source_dir / ".git" / "HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                ref = head.split(" ", 1)[1].strip()
                ref_file = source_dir / ".git" / ref
                if ref_file.is_file():
                    sha = ref_file.read_text(encoding="utf-8").strip()[:7]
                    version = f"{version}-{sha}"
        except OSError:
            pass

    tmp = Path(tempfile.mkdtemp(prefix="coce-panel-pack-"))
    zip_path = tmp / f"panel-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in _iter_files(backend):
            zf.write(f, Path("backend") / f.relative_to(backend))
        prefix = "frontend/dist" if frontend_payload == dist else "frontend"
        for f in _iter_files(frontend_payload):
            zf.write(f, Path(prefix) / f.relative_to(frontend_payload))
        zf.writestr(
            "manifest.json",
            (
                '{\n'
                f'  "kind": "panel",\n'
                f'  "version": "{version}",\n'
                f'  "excludes": ["data/", "*.db", ".env", "node_modules/"]\n'
                "}\n"
            ),
        )
    return zip_path, version
