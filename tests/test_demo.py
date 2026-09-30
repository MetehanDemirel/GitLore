from __future__ import annotations

from collections import Counter
from pathlib import Path

import git
import pytest

from src import config, demo


@pytest.fixture
def demo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config, "DEMO_DIR", tmp_path / "demo")
    return tmp_path / "demo"


def test_demo_history_is_identical_on_every_build(demo_dir: Path, tmp_path: Path, monkeypatch):
    first = git.Repo(demo.ensure_demo()).head.commit.hexsha
    monkeypatch.setattr(config, "DEMO_DIR", tmp_path / "demo2")
    second = git.Repo(demo.ensure_demo()).head.commit.hexsha
    assert first == second


def test_demo_story(demo_dir: Path):
    repo = git.Repo(demo.ensure_demo())
    commits = list(repo.iter_commits("main"))
    subjects = [c.summary for c in commits]
    assert len(commits) > 150
    assert len(Counter(c.author.name for c in commits)) == 8
    for key in ["Switch login from server sessions to JWT tokens", "Fix SQL injection in search",
                "refactor: split into core, api and cli packages", 'Revert "Add a web dashboard"',
                "Add CSV export again, now safe on Windows"]:
        assert key in subjects, key
    assert sum(1 for c in commits if len(c.parents) == 2) >= 2, "has pull-request merges"
    assert {t.name for t in repo.tags} >= {"v1.0.0", "v1.1.1", "v2.0.0", "v2.2.1"}
    assert "experiment/graphql" in {b.name for b in repo.branches}, "an unmerged branch for the branch view"
    files = set(repo.git.ls_files().split())
    assert {"taskflow/core/auth.py", "taskflow/core/storage.py", "taskflow/api/server.py"} <= files
    assert "from taskflow.core.models import Task" in (demo.repo_path() / "taskflow/core/storage.py").read_text()
    assert not repo.is_dirty(untracked_files=True)


def test_demo_code_is_valid_python(demo_dir: Path):
    path = demo.ensure_demo()
    for py in path.rglob("*.py"):
        compile(py.read_text(encoding="utf-8"), str(py), "exec")


def test_ensure_demo_does_not_rebuild_a_current_repo(demo_dir: Path):
    path = demo.ensure_demo()
    (path / "notes.txt").write_text("my own experiment")
    assert demo.ensure_demo() == path
    assert (path / "notes.txt").exists()


def test_interrupted_build_is_replaced(demo_dir: Path):
    broken = demo.repo_path()
    broken.mkdir(parents=True)
    (broken / "half-written.txt").write_text("x")
    repo = git.Repo(demo.ensure_demo())
    assert repo.head.is_valid() and demo.is_current()


def test_older_demo_version_is_upgraded(demo_dir: Path):
    old = demo_dir / "taskflow"
    git.Repo.init(old)
    path = demo.ensure_demo()
    assert path != old and demo.is_current()
    assert not old.exists(), "the old version's folder is removed when possible"
