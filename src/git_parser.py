"""Extract structured commit data from a local Git repository (Phase 2)."""

from __future__ import annotations

from typing import TypedDict

from src import config


class Commit(TypedDict):
    hash: str
    short_hash: str
    author: str
    date: str          # ISO 8601
    message: str
    files_changed: list[str]
    diff_summary: str  # truncated to config.MAX_DIFF_CHARS_PER_COMMIT


class RepoError(Exception):
    """Raised with a user-friendly message for bad paths, non-repos, empty repos, or missing git."""


def get_commits(repo_path: str, max_count: int = config.DEFAULT_COMMIT_COUNT) -> list[Commit]:
    """Return up to `max_count` commits, newest first."""
    raise NotImplementedError("Phase 2")
