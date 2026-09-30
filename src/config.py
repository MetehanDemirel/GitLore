"""Single source of truth for paths, model presets, and tuning limits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.2.1"  # keep in sync with CHANGELOG.md

# --- Paths -------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
# GITLORE_DATA_DIR moves everything GitLore stores (models, index, projects, demo) elsewhere.
DATA_DIR = Path(os.environ["GITLORE_DATA_DIR"]) if os.environ.get("GITLORE_DATA_DIR") else ROOT_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
CHROMA_DIR = DATA_DIR / "chroma"
DB_PATH = DATA_DIR / "gitlore.db"          # projects, chats, settings (SQLite)
DEMO_DIR = DATA_DIR / "demo"               # the built-in demo repository is generated here
VENDOR_DIR = DATA_DIR / "vendor"           # Monaco editor, downloaded on first launch
WEB_DIR = ROOT_DIR / "web"                 # the browser UI (static files, no build step)

# --- Web server ----------------------------------------------------------------
HOST = "127.0.0.1"                         # only reachable from this computer
PORT = 8501

# --- UI --------------------------------------------------------------------------
LANGUAGES = {"en": "English", "tr": "Türkçe", "fr": "Français", "de": "Deutsch"}
DEFAULT_LANGUAGE = "en"
THEMES = ("system", "light", "dark")

# Monaco (VS Code's editor). Pinned and integrity-checked; only package/min/vs is kept (~26 MB).
# The AMD build is deprecated upstream: upgrading past 0.57 means moving to its ESM build.
MONACO_VERSION = "0.57.0"
MONACO_TARBALL = f"https://registry.npmjs.org/monaco-editor/-/monaco-editor-{MONACO_VERSION}.tgz"
MONACO_INTEGRITY = "sha512-5BkI9KGoqrNvBGUe15/QlZq3OooZ8WLg1AxTpaqHRCP3HNpzPPZKE2EDz8M7c+VRmCeUw1Brp4cx/PWm3kI/5A=="


# --- Models ------------------------------------------------------------------
@dataclass(frozen=True)
class ModelPreset:
    label: str
    repo_id: str
    filename: str
    size_gb: float


# Chosen by benchmark (PLAN.md, "Model choice"): of 9 small models, Qwen3-1.7B was as fast as the
# previous default and the only one that said "not in the commits" instead of inventing an answer.
MODEL_PRESETS: dict[str, ModelPreset] = {
    "qwen3-1.7b": ModelPreset(
        label="Qwen3 1.7B — recommended (1.1 GB)",
        repo_id="unsloth/Qwen3-1.7B-GGUF",
        filename="Qwen3-1.7B-Q4_K_M.gguf",
        size_gb=1.11,
    ),
}
DEFAULT_PRESET = "qwen3-1.7b"


# --- LLM runtime -------------------------------------------------------------
N_CTX = 4096               # total context window (tokens)
ANSWER_TOKENS = 512        # reserved for the model's reply
# CPU prompt reading runs at only ~110-130 tokens/s, so the prompt size directly sets the wait before
# the first word appears. ~1,800 tokens ≈ 15 s on a mid-range laptop; the full 3,500 would be ~30 s.
MAX_PROMPT_TOKENS = 1800
PROMPT_DIFF_CHARS = 600    # per-commit diff shown to the LLM (the index keeps MAX_DIFF_CHARS_PER_COMMIT)
TEMPERATURE = 0.2
N_GPU_LAYERS = -1          # no-op on the default CPU build; used if someone installs a GPU build


def default_n_threads() -> int:
    """Threads for generating tokens: approx. physical cores (hyperthreads don't help here)."""
    return max(1, (os.cpu_count() or 2) // 2)


def default_n_threads_batch() -> int:
    """Threads for reading the prompt: all logical cores (~12% faster in benchmarks)."""
    return max(1, os.cpu_count() or 2)


# --- Git ingestion -----------------------------------------------------------
DEFAULT_COMMIT_COUNT = 200
MAX_DIFF_CHARS_PER_COMMIT = 1500   # truncation for both indexing and prompting
MAX_FILES_LISTED = 30
# Files whose diff content is noise for "why did this change?" questions.
# They still appear in files_changed; only their line-by-line diff is skipped.
NOISY_DIFF_FILES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
    "Cargo.lock", "Gemfile.lock", "composer.lock", "go.sum",
)
NOISY_DIFF_SUFFIXES = (".min.js", ".min.css", ".map", ".svg", ".ipynb")

# --- Retrieval ---------------------------------------------------------------
TOP_K = 5

# --- App lifecycle -----------------------------------------------------------
IDLE_SHUTDOWN_SECONDS = 30  # exit after the last browser tab has been closed this long
HEARTBEAT_SECONDS = 10      # how often an open tab pings the server
