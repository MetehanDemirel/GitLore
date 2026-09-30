from __future__ import annotations

from pathlib import Path

import pytest

from src import config, vector_store
from src.git_parser import get_commits


@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")


@pytest.fixture
def history(rb):
    """A small repo with clearly distinct topics."""
    rb.commit("Switch login from server sessions to JWT tokens\n\nSessions didn't scale across pods.",
              {"auth/login.py": "def login(user):\n    return issue_jwt(user)\n"})
    rb.commit("Fix typo in README", {"README.md": "# Project\nInstall with pip.\n"})
    rb.commit("Add database migration for orders table",
              {"migrations/0002_orders.sql": "CREATE TABLE orders (id INTEGER PRIMARY KEY);\n"})
    rb.commit("Speed up CSV export with streaming writer",
              {"export/csv.py": "def export(rows):\n    yield from rows\n"})
    return rb


def test_index_is_incremental(history):
    path = str(history.path)
    assert vector_store.index_commits(path, get_commits(path)) == 4
    assert vector_store.count(path) == 4
    assert vector_store.index_commits(path, get_commits(path)) == 0

    history.commit("Add rate limiting to the API", {"api/limits.py": "LIMIT = 100\n"})
    assert vector_store.index_commits(path, get_commits(path)) == 1
    assert vector_store.count(path) == 5


def test_search_finds_semantically_relevant_commit(history):
    path = str(history.path)
    vector_store.index_commits(path, get_commits(path))

    assert "JWT" in vector_store.search(path, "why did the authentication change?", top_k=1)[0]["message"]
    assert "migration" in vector_store.search(path, "when was the orders schema created?", top_k=1)[0]["message"]


def test_search_round_trips_all_commit_fields(history):
    path = str(history.path)
    commits = get_commits(path)
    vector_store.index_commits(path, commits)
    by_hash = {c["hash"]: c for c in commits}
    for hit in vector_store.search(path, "anything", top_k=4):
        assert hit == by_hash[hit["hash"]]


def test_commit_hash_in_question_is_matched_exactly(history):
    path = str(history.path)
    commits = get_commits(path)
    vector_store.index_commits(path, commits)
    readme = next(c for c in commits if "README" in c["message"])

    for token in (readme["short_hash"], readme["hash"][:10], readme["hash"]):
        hits = vector_store.search(path, f"what did {token} do?", top_k=3)
        assert hits[0]["hash"] == readme["hash"]
        assert len({h["hash"] for h in hits}) == len(hits)  # no duplicates


def test_subfolder_uses_same_index(history):
    path = str(history.path)
    vector_store.index_commits(path, get_commits(path))
    assert vector_store.count(str(history.path / "auth")) == 4


def test_repos_are_isolated(history, make_repo):
    other = make_repo("other")
    other.commit("Unrelated", {"x.txt": "x\n"})
    vector_store.index_commits(str(history.path), get_commits(str(history.path)))
    assert vector_store.count(str(other.path)) == 0


def test_reset_and_empty_search(history):
    path = str(history.path)
    assert vector_store.search(path, "anything") == []
    vector_store.index_commits(path, get_commits(path))
    vector_store.reset(path)
    assert vector_store.count(path) == 0
    assert vector_store.search(path, "login") == []


def test_progress_callback_reports_completion(history):
    path = str(history.path)
    calls = []
    vector_store.index_commits(path, get_commits(path), on_progress=lambda d, t: calls.append((d, t)))
    assert calls[-1] == (4, 4)
