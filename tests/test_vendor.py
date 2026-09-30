from __future__ import annotations

import base64
import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from src import config, vendor


def fake_tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in [("package/min/vs/loader.js", b"// loader"),
                              ("package/min/vs/editor/editor.main.js", b"// editor"),
                              ("package/esm/unused.js", b"skip me"),
                              ("package/min/vs/../../escape.js", b"evil")]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = fake_tarball()
    monkeypatch.setattr(config, "VENDOR_DIR", tmp_path / "vendor")
    monkeypatch.setattr(config, "MONACO_INTEGRITY", "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode())
    calls = []
    monkeypatch.setattr(vendor, "_download", lambda url, cb: calls.append(url) or data)
    return tmp_path, calls


def test_extracts_only_min_vs_and_skips_after(setup):
    tmp_path, calls = setup
    assert not vendor.monaco_ready()
    path = vendor.ensure_monaco()
    assert vendor.monaco_ready()
    assert (path / "loader.js").read_bytes() == b"// loader"
    assert not list((tmp_path / "vendor").rglob("unused.js"))
    assert not list(tmp_path.rglob("escape.js")), "paths escaping the target folder are ignored"
    vendor.ensure_monaco()
    assert len(calls) == 1, "second call does not download again"


def test_integrity_mismatch_is_refused(setup, monkeypatch):
    monkeypatch.setattr(config, "MONACO_INTEGRITY", "sha512-" + base64.b64encode(b"x" * 64).decode())
    with pytest.raises(vendor.VendorError, match="integrity"):
        vendor.ensure_monaco()
    assert not vendor.monaco_ready()


def test_network_error_is_friendly(setup, monkeypatch):
    def boom(url, cb):
        raise OSError("no network")
    monkeypatch.setattr(vendor, "_download", boom)
    with pytest.raises(vendor.VendorError, match="internet"):
        vendor.ensure_monaco()
