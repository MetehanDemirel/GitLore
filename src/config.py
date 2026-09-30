"""Single source of truth for paths, model presets, and tuning limits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --- Paths -------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
CHROMA_DIR = DATA_DIR / "chroma"


# --- Models ------------------------------------------------------------------
@dataclass(frozen=True)
class ModelPreset:
    label: str
    repo_id: str
    filename: str
    size_gb: float


MODEL_PRESETS: dict[str, ModelPreset] = {
    "fast": ModelPreset(
        label="Fast — Qwen2.5-Coder 1.5B (1.1 GB)",
        repo_id="Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        filename="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        size_gb=1.12,
    ),
    "better": ModelPreset(
        label="Better answers — Qwen2.5-Coder 3B (2.1 GB, slower)",
        repo_id="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
        filename="qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        size_gb=2.1,
    ),
}
DEFAULT_PRESET = "fast"


# --- LLM runtime -------------------------------------------------------------
N_CTX = 4096               # total context window (tokens)
ANSWER_TOKENS = 512        # reserved for the model's reply
PROMPT_OVERHEAD_TOKENS = 300  # system prompt + question + formatting
TEMPERATURE = 0.2
N_GPU_LAYERS = -1          # no-op on the default CPU build; used if someone installs a GPU build


def default_n_threads() -> int:
    """Approximate physical cores; hyperthreads don't help llama.cpp much."""
    return max(1, (os.cpu_count() or 2) // 2)


# --- Git ingestion -----------------------------------------------------------
DEFAULT_COMMIT_COUNT = 200
MAX_COMMIT_COUNT = 2000
MAX_DIFF_CHARS_PER_COMMIT = 1500   # truncation for both indexing and prompting
MAX_FILES_LISTED = 30

# --- Retrieval ---------------------------------------------------------------
TOP_K = 5

# --- App lifecycle -----------------------------------------------------------
IDLE_SHUTDOWN_SECONDS = 30  # exit after the last browser tab has been closed this long
