"""Downloads Monaco (VS Code's editor) once, on first launch.

Only `package/min/vs` (~26 MB) of the pinned npm tarball is kept. The download is checked against the
npm sha512 integrity hash, and the folder is swapped in atomically, so an interrupted download never
leaves a half-installed editor behind.
"""

from __future__ import annotations

import base64
import hashlib
import io
import shutil
import tarfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from src import config

ProgressCallback = Callable[[int, int], None]  # (bytes_done, bytes_total)
_PREFIX = "package/min/vs/"


class VendorError(Exception):
    """Raised with a user-friendly message."""


def monaco_dir() -> Path:
    return config.VENDOR_DIR / f"monaco-{config.MONACO_VERSION}" / "vs"


def monaco_ready() -> bool:
    return (monaco_dir() / "loader.js").is_file() and (monaco_dir() / "editor" / "editor.main.js").is_file()


def ensure_monaco(on_progress: ProgressCallback | None = None) -> Path:
    if monaco_ready():
        return monaco_dir()
    try:
        data = _download(config.MONACO_TARBALL, on_progress)
    except OSError as e:
        raise VendorError(f"Could not download the editor — check your internet connection. ({type(e).__name__})") from None
    algo, _, expected = config.MONACO_INTEGRITY.partition("-")
    actual = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if actual != expected:
        raise VendorError("The downloaded editor files failed their integrity check. Try again later.")

    final = monaco_dir()
    staging = final.parent.with_name(final.parent.name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith(_PREFIX):
                continue
            rel = Path(member.name[len(_PREFIX):])
            if rel.is_absolute() or ".." in rel.parts:
                continue  # never write outside the target folder
            target = staging / "vs" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
    shutil.rmtree(final.parent, ignore_errors=True)
    staging.rename(final.parent)
    return final


def _download(url: str, on_progress: ProgressCallback | None) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        chunks, done = [], 0
        while chunk := response.read(256 * 1024):
            chunks.append(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total or done)
    return b"".join(chunks)
