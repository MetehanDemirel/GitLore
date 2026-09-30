from __future__ import annotations

from pathlib import Path

import pytest

from src import config, model_manager
from src.config import ModelPreset
from src.model_manager import ModelError

FAKE = ModelPreset(label="Fake", repo_id="nobody/nothing", filename="fake.gguf", size_gb=0.0)


@pytest.fixture(autouse=True)
def isolated_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")


def test_custom_preset_validation():
    p = model_manager.custom_preset(" owner/repo ", " model.Q4_K_M.gguf ")
    assert (p.repo_id, p.filename) == ("owner/repo", "model.Q4_K_M.gguf")
    for repo, fname in [("noslash", "m.gguf"), ("a/b/c", "m.gguf"), ("owner/repo", "model.bin")]:
        with pytest.raises(ModelError):
            model_manager.custom_preset(repo, fname)


def test_existing_model_is_not_downloaded_again():
    path = model_manager.model_path(FAKE)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"GGUF")
    assert model_manager.is_downloaded(FAKE)
    assert model_manager.ensure_model(FAKE) == path  # no network call: repo doesn't exist


def test_delete_model():
    path = model_manager.model_path(FAKE)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"GGUF")
    model_manager.delete_model(FAKE)
    assert not model_manager.is_downloaded(FAKE)
    model_manager.delete_model(FAKE)  # deleting twice is fine


def test_load_missing_model_raises_friendly_error():
    with pytest.raises(ModelError, match="not downloaded"):
        model_manager.load_llm(FAKE)


# llama-cpp-python 0.3.19 raises a harmless AttributeError in __del__ after a failed load.
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_load_invalid_file_raises_friendly_error():
    path = model_manager.model_path(FAKE)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"this is not a gguf file")
    with pytest.raises(ModelError, match="Could not load"):
        model_manager.load_llm(FAKE)
