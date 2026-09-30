"""Download GGUF models from Hugging Face and load them with llama.cpp (CPU)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from src import config
from src.config import ModelPreset

if TYPE_CHECKING:
    from llama_cpp import Llama

ProgressCallback = Callable[[int, int], None]  # (bytes_done, bytes_total)


class ModelError(Exception):
    """Raised with a user-friendly message when a model can't be downloaded or loaded."""


def custom_preset(repo_id: str, filename: str) -> ModelPreset:
    """A preset for any GGUF file on Hugging Face (advanced option in the UI)."""
    repo_id, filename = repo_id.strip(), filename.strip()
    if repo_id.count("/") != 1 or not filename.lower().endswith(".gguf"):
        raise ModelError("Enter a Hugging Face repo like 'owner/name' and a file name ending in .gguf")
    return ModelPreset(label=f"Custom — {filename}", repo_id=repo_id, filename=filename, size_gb=0.0)


def model_path(preset: ModelPreset) -> Path:
    """Local path where the preset's GGUF file lives (may not exist yet)."""
    return config.MODELS_DIR / preset.filename


def is_downloaded(preset: ModelPreset) -> bool:
    return model_path(preset).is_file()


def ensure_model(preset: ModelPreset, on_progress: ProgressCallback | None = None) -> Path:
    """Download the preset's model into data/models/ if missing (resumes partial downloads)."""
    path = model_path(preset)
    if path.is_file():
        return path

    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError

    try:
        downloaded = hf_hub_download(
            repo_id=preset.repo_id,
            filename=preset.filename,
            local_dir=config.MODELS_DIR,
            tqdm_class=_progress_tqdm(on_progress) if on_progress else None,
        )
    except (RepositoryNotFoundError, EntryNotFoundError):
        raise ModelError(f"'{preset.filename}' was not found in '{preset.repo_id}' on Hugging Face.") from None
    except OSError as e:  # includes connection errors
        raise ModelError(f"Download failed — check your internet connection. ({e.__class__.__name__})") from None
    return Path(downloaded)


def delete_model(preset: ModelPreset) -> None:
    """Remove a downloaded model file to free disk space."""
    model_path(preset).unlink(missing_ok=True)


def load_llm(preset: ModelPreset) -> "Llama":
    """Load a downloaded model for inference. Cache the result (st.cache_resource) — loading takes seconds."""
    from llama_cpp import Llama

    path = model_path(preset)
    if not path.is_file():
        raise ModelError("Model is not downloaded yet.")
    try:
        return Llama(
            model_path=str(path),
            n_ctx=config.N_CTX,
            n_threads=config.default_n_threads(),
            n_threads_batch=config.default_n_threads_batch(),
            n_gpu_layers=config.N_GPU_LAYERS,
            verbose=False,
        )
    except ValueError as e:
        raise ModelError(f"Could not load the model (is it a valid, supported GGUF file?): {e}") from None


def _progress_tqdm(on_progress: ProgressCallback):
    """A tqdm subclass that forwards byte progress to `on_progress` instead of drawing a bar."""
    from tqdm import tqdm

    class _Progress(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = False
            kwargs.setdefault("file", _NullWriter())
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            result = super().update(n)
            if self.total:
                on_progress(int(self.n), int(self.total))
            return result

    return _Progress


class _NullWriter:
    def write(self, *_):
        pass

    def flush(self):
        pass
