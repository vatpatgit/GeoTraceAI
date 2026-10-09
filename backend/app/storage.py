"""Local-filesystem object storage with traversal protection, streamed uploads and temp cleanup.

All database rows store *relative* paths; absolute paths and the storage root are never exposed to clients.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

from app.config import settings


class UploadTooLarge(Exception):
    pass


class StoragePathError(ValueError):
    pass


def storage_root() -> Path:
    root = Path(settings.STORAGE_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve(rel: str | os.PathLike[str]) -> Path:
    """Join ``rel`` onto the storage root, refusing anything that escapes it (``..``, absolute paths, symlink tricks)."""
    root = storage_root()
    rel_s = str(rel)
    if os.path.isabs(rel_s) or rel_s.startswith(("/", "\\")):
        raise StoragePathError("absolute paths are not allowed")
    target = (root / rel_s).resolve()
    if target != root and root not in target.parents:
        raise StoragePathError("path escapes the storage root")
    return target


def relative(path: Path) -> str:
    return path.resolve().relative_to(storage_root()).as_posix()


def asset_dir(asset_id: uuid.UUID | str) -> Path:
    d = resolve(f"imagery/{asset_id}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def analysis_dir(analysis_id: uuid.UUID | str) -> Path:
    d = resolve(f"analyses/{analysis_id}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def temp_dir() -> Path:
    d = resolve("tmp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_workdir(prefix: str = "job") -> Path:
    return Path(tempfile.mkdtemp(prefix=f"{prefix}-", dir=temp_dir()))


def remove_tree(rel: str) -> None:
    p = resolve(rel)
    if p.exists() and p != storage_root():
        shutil.rmtree(p, ignore_errors=True)


def cleanup_temp(max_age_hours: float | None = None) -> int:
    """Delete temp work directories older than the retention window. Returns the number removed."""
    hours = settings.TEMP_RETENTION_HOURS if max_age_hours is None else max_age_hours
    cutoff = time.time() - hours * 3600
    removed = 0
    for child in temp_dir().iterdir():
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ \-()\[\]]+")


def sanitize_filename(name: str | None, default: str = "upload.tif") -> str:
    """For *display only*: never used to build a filesystem path."""
    if not name:
        return default
    base = os.path.basename(name.replace("\\", "/"))
    base = _SAFE_NAME.sub("_", base).strip(" .")
    return (base or default)[:200]


async def save_stream(chunks: AsyncIterator[bytes], dest: Path, *, max_bytes: int) -> tuple[int, str]:
    """Write an async byte stream to ``dest`` enforcing a size cap; returns (size, sha256). Partial files are removed."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as fh:
            async for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge(f"upload exceeds the {max_bytes // (1024 * 1024)} MB limit")
                h.update(chunk)
                fh.write(chunk)
        os.replace(tmp, dest)
        return size, h.hexdigest()
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
