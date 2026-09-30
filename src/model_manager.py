"""Download GGUF models from Hugging Face and load them with llama.cpp (Phase 4)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src import config

if TYPE_CHECKING:
    from llama_cpp import Llama


def model_path(preset_key: str = config.DEFAULT_PRESET) -> Path:
    """Local path where the preset's GGUF file lives (may not exist yet)."""
    return config.MODELS_DIR / config.MODEL_PRESETS[preset_key].filename


def is_downloaded(preset_key: str = config.DEFAULT_PRESET) -> bool:
    return model_path(preset_key).is_file()


def ensure_model(preset_key: str = config.DEFAULT_PRESET) -> Path:
    """Download the preset's model into data/models/ if missing; return its path."""
    raise NotImplementedError("Phase 4")


def load_llm(preset_key: str = config.DEFAULT_PRESET) -> "Llama":
    """Load the model for CPU inference (cache the result with st.cache_resource in app.py)."""
    raise NotImplementedError("Phase 4")
