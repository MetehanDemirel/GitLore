"""Persist and search commit embeddings with ChromaDB (Phase 3).

Uses Chroma's built-in all-MiniLM-L6-v2 embedder (ONNX) — no PyTorch.
One collection per repository, keyed by a hash of its absolute path.
"""

from __future__ import annotations

from src import config
from src.git_parser import Commit


def collection_name(repo_path: str) -> str:
    """Stable, Chroma-valid collection name for a repo path."""
    raise NotImplementedError("Phase 3")


def index_commits(repo_path: str, commits: list[Commit]) -> int:
    """Add commits not already indexed. Returns the number of newly added commits."""
    raise NotImplementedError("Phase 3")


def search(repo_path: str, query: str, top_k: int = config.TOP_K) -> list[Commit]:
    """Return the `top_k` commits most semantically relevant to `query`."""
    raise NotImplementedError("Phase 3")
