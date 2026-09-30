from __future__ import annotations

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
    subjects = [c.summary for c in repo.iter_commits("HEAD")]
    assert len(subjects) == 16
    assert "Switch login from server sessions to JWT tokens" in subjects
    assert any(c.parents and len(c.parents) == 2 for c in repo.iter_commits("HEAD")), "has a merge commit"
    assert 'Revert "Add CSV export"' in subjects
    assert repo.head.commit.summary == "Release 1.0"
    assert sorted(repo.git.ls_files().split()) == [
        "README.md", "requirements.txt", "taskflow/__init__.py", "taskflow/auth.py",
        "taskflow/models.py", "taskflow/storage.py"]
    assert "from taskflow.models import Task" in (demo.repo_path() / "taskflow/storage.py").read_text()
    assert not repo.is_dirty(untracked_files=True)


def test_ensure_demo_does_not_rebuild_an_existing_repo(demo_dir: Path):
    path = demo.ensure_demo()
    (path / "notes.txt").write_text("my own experiment")
    assert demo.ensure_demo() == path
    assert (path / "notes.txt").exists()


def test_interrupted_build_is_replaced(demo_dir: Path):
    broken = demo.repo_path()
    broken.mkdir(parents=True)
    (broken / "half-written.txt").write_text("x")
    repo = git.Repo(demo.ensure_demo())
    assert repo.head.commit.summary == "Release 1.0"
