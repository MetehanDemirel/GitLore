from pathlib import Path

import git
import pytest


class RepoBuilder:
    """Tiny helper that makes real commits in a throwaway repo."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.repo = git.Repo.init(path, initial_branch="main")
        with self.repo.config_writer() as cw:
            cw.set_value("user", "name", "Ada Lovelace")
            cw.set_value("user", "email", "ada@example.com")
            cw.set_value("commit", "gpgsign", "false")

    def commit(self, message: str, files: dict[str, str | bytes | None]) -> str:
        for name, content in files.items():
            target = self.path / name
            if content is None:
                self.repo.git.rm(name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8", newline="\n")
            self.repo.git.add(name)
        self.repo.git.commit("-m", message, "--allow-empty")
        return self.repo.head.commit.hexsha


@pytest.fixture
def rb(tmp_path: Path) -> RepoBuilder:
    return RepoBuilder(tmp_path / "repo")
