"""Persist and search commit embeddings with ChromaDB.

Uses Chroma's built-in all-MiniLM-L6-v2 embedder (ONNX, ~80 MB, downloaded on first use) — no PyTorch.
One collection per repository, keyed by a hash of the repo's root folder, stored under data/chroma/.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from functools import lru_cache

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from src import config
from src.git_parser import Commit, open_repo

_EMBED_BATCH = 64  # small batches keep progress updates smooth; embedding dominates the cost
_HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")

ProgressCallback = Callable[[int, int], None]  # (done, total)


@lru_cache(maxsize=None)
def _client(path: str) -> chromadb.ClientAPI:
    # Local, private app: never send telemetry.
    return chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))


def repo_root(repo_path: str) -> str:
    """Normalized root folder of the repo containing `repo_path` (subfolders map to the same repo)."""
    return os.path.normcase(os.path.realpath(open_repo(repo_path).working_tree_dir))


def _name_for_root(root: str) -> str:
    return "repo-" + hashlib.sha1(root.encode("utf-8")).hexdigest()[:16]


def collection_name(repo_path: str) -> str:
    """Stable, Chroma-valid collection name for a repo path."""
    return _name_for_root(repo_root(repo_path))


def _collection(repo_path: str):
    root = repo_root(repo_path)
    return _client(str(config.CHROMA_DIR)).get_or_create_collection(
        name=_name_for_root(root),
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=DefaultEmbeddingFunction(),
        metadata={"repo_root": root},
    )


def _document(c: Commit) -> str:
    # MiniLM only "sees" the first ~256 tokens, so put the most meaningful text first.
    return f"{c['message']}\n\nFiles: {', '.join(c['files_changed'])}\n\n{c['diff_summary']}"


def _metadata(c: Commit) -> dict[str, str]:
    return {
        "short_hash": c["short_hash"],
        "author": c["author"],
        "date": c["date"],
        "message": c["message"],
        "files_changed": "\n".join(c["files_changed"]),
        "diff_summary": c["diff_summary"],
    }


def _to_commit(hash_: str, meta: dict) -> Commit:
    return Commit(
        hash=hash_,
        short_hash=meta["short_hash"],
        author=meta["author"],
        date=meta["date"],
        message=meta["message"],
        files_changed=[f for f in meta["files_changed"].split("\n") if f],
        diff_summary=meta["diff_summary"],
    )


def index_commits(repo_path: str, commits: list[Commit], on_progress: ProgressCallback | None = None) -> int:
    """Add commits not already indexed. Returns the number of newly added commits."""
    col = _collection(repo_path)
    unique = list({c["hash"]: c for c in commits}.values())
    existing: set[str] = set()
    for i in range(0, len(unique), 500):
        ids = [c["hash"] for c in unique[i : i + 500]]
        existing.update(col.get(ids=ids, include=[])["ids"])
    new = [c for c in unique if c["hash"] not in existing]

    for i in range(0, len(new), _EMBED_BATCH):
        batch = new[i : i + _EMBED_BATCH]
        col.add(
            ids=[c["hash"] for c in batch],
            documents=[_document(c) for c in batch],
            metadatas=[_metadata(c) for c in batch],
        )
        if on_progress:
            on_progress(i + len(batch), len(new))
    return len(new)


def count(repo_path: str) -> int:
    """Number of commits indexed for this repo."""
    return _collection(repo_path).count()


def reset(repo_path: str) -> None:
    """Delete this repo's index (e.g. after a history rewrite)."""
    client = _client(str(config.CHROMA_DIR))
    name = collection_name(repo_path)
    if name in {c.name for c in client.list_collections()}:
        client.delete_collection(name)


def search(repo_path: str, query: str, top_k: int = config.TOP_K) -> list[Commit]:
    """Return up to `top_k` commits most relevant to `query`, best first.

    Commit hashes mentioned in the query (e.g. "what did a8ce8ff do?") are matched exactly and
    ranked first, since embeddings can't match hex strings.
    """
    col = _collection(repo_path)
    total = col.count()
    if total == 0 or not query.strip():
        return []

    results: dict[str, Commit] = {}
    for token in _HASH_RE.findall(query.lower()):
        hit = col.get(where={"short_hash": token[:7]}, include=["metadatas"])
        for hash_, meta in zip(hit["ids"], hit["metadatas"]):
            if hash_.startswith(token):
                results.setdefault(hash_, _to_commit(hash_, meta))

    res = col.query(query_texts=[query], n_results=min(top_k, total), include=["metadatas"])
    for hash_, meta in zip(res["ids"][0], res["metadatas"][0]):
        results.setdefault(hash_, _to_commit(hash_, meta))
    return list(results.values())[:top_k]
