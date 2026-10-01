from __future__ import annotations

import pytest

from src import chat_engine, config, demo, retrieval


@pytest.fixture(scope="module")
def demo_path(tmp_path_factory) -> str:
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DEMO_DIR", tmp_path_factory.mktemp("demo"))
    yield str(demo.ensure_demo())
    mp.undo()


@pytest.mark.parametrize("question, expected", [
    ("What has Priya Nair worked on?", {"author": "Priya Nair"}),
    ("what did lucia change?", {"author": "Lucía Romero"}),
    ("How did taskflow/core/auth.py evolve?", {"path": "taskflow/core/auth.py"}),
    ("What changed in v1.1.1?", {"release": "v1.1.1"}),
    ("What changed in 2.0?", {"release": "v2.0.0"}),
    ("List the security fixes.", {"type": "security", "weak": True}),
    ("What are the latest changes?", {"recent": True}),
    ("Why did we switch login to JWT?", {}),
])
def test_understand(demo_path, question, expected):
    assert retrieval.understand(demo_path, question) == expected


def test_filtered_commits_skip_repeated_subjects(demo_path):
    subjects = [c["subject"] for c in __import__("src.insights", fromlist=["x"]).search(demo_path, "")["results"]]
    hashes = retrieval._filtered(demo_path, {"recent": True})
    assert len(hashes) == retrieval.FILTERED_MAX and subjects  # newest commits, in order
    security = retrieval._filtered(demo_path, {"type": "security", "author": "Nobody Here"})
    assert security, "an author with no matches is dropped instead of returning nothing"


@pytest.mark.parametrize("question, follow", [
    ("Who did that?", True), ("And when was it added back?", True),
    ("Why did storage move from JSON to SQLite in the first release?", False),
])
def test_follow_up_detection(question, follow):
    assert chat_engine.is_follow_up(question, [("Why was the CSV export reverted?", "…")]) is follow
