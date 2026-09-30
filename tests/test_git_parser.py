from pathlib import Path

import git
import pytest

from src import config
from src.git_parser import RepoError, get_commits


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


def test_basic_fields_and_newest_first(rb: RepoBuilder):
    first = rb.commit("Add app", {"app.py": "print('hi')\n"})
    second = rb.commit("Change greeting", {"app.py": "print('hello')\n"})

    commits = get_commits(str(rb.path))

    assert [c["hash"] for c in commits] == [second, first]
    top = commits[0]
    assert top["short_hash"] == second[:7]
    assert top["author"] == "Ada Lovelace"
    assert top["date"][:4].isdigit() and "T" in top["date"]
    assert top["message"] == "Change greeting"
    assert top["files_changed"] == ["app.py"]
    assert "-print('hi')" in top["diff_summary"]
    assert "+print('hello')" in top["diff_summary"]


def test_diff_noise_lines_are_dropped(rb: RepoBuilder):
    rb.commit("Add", {"a.txt": "one\n"})
    summary = get_commits(str(rb.path))[0]["diff_summary"]
    assert "index " not in summary
    assert "+++ " not in summary and "--- " not in summary
    assert "(new file)" in summary


def test_multiline_message_is_preserved(rb: RepoBuilder):
    rb.commit("Switch auth to JWT\n\nSessions didn't scale across pods.\nSee issue 42.", {"auth.py": "x = 1\n"})
    msg = get_commits(str(rb.path))[0]["message"]
    assert msg.startswith("Switch auth to JWT")
    assert "Sessions didn't scale across pods." in msg
    assert msg.endswith("See issue 42.")


def test_message_that_looks_like_a_diff_is_not_parsed_as_one(rb: RepoBuilder):
    rb.commit("Doc\n\ndiff --git a/fake.py b/fake.py\n+not real", {"real.py": "y = 2\n"})
    c = get_commits(str(rb.path))[0]
    assert c["files_changed"] == ["real.py"]
    assert "diff --git a/fake.py" in c["message"]


def test_max_count(rb: RepoBuilder):
    for i in range(5):
        rb.commit(f"c{i}", {"f.txt": f"{i}\n"})
    commits = get_commits(str(rb.path), max_count=3)
    assert [c["message"] for c in commits] == ["c4", "c3", "c2"]


def test_lock_file_is_listed_but_diff_omitted(rb: RepoBuilder):
    rb.commit("Bump deps", {"package-lock.json": '{"lockfileVersion": 3}\n', "src/main.js": "go()\n"})
    c = get_commits(str(rb.path))[0]
    assert set(c["files_changed"]) == {"package-lock.json", "src/main.js"}
    assert "lockfileVersion" not in c["diff_summary"]
    assert "diff omitted" in c["diff_summary"]
    assert "+go()" in c["diff_summary"]


def test_binary_and_deleted_files(rb: RepoBuilder):
    rb.commit("Add logo and notes", {"logo.png": b"\x89PNG\x00\x01\x02", "notes.txt": "n\n"})
    rb.commit("Remove notes", {"notes.txt": None})
    commits = get_commits(str(rb.path))
    assert "(deleted file)" in commits[0]["diff_summary"]
    assert "(binary file changed)" in commits[1]["diff_summary"]


def test_large_diff_is_truncated(rb: RepoBuilder):
    big = "".join(f"line number {i}\n" for i in range(2000))
    rb.commit("Huge change", {"big.txt": big})
    summary = get_commits(str(rb.path))[0]["diff_summary"]
    assert len(summary) <= config.MAX_DIFF_CHARS_PER_COMMIT + 50
    assert summary.endswith("(diff truncated)")


def test_merge_commit_does_not_break_parsing(rb: RepoBuilder):
    rb.commit("base", {"a.txt": "a\n"})
    rb.repo.git.checkout("-b", "feature")
    rb.commit("feature work", {"b.txt": "b\n"})
    rb.repo.git.checkout("main")
    rb.commit("main work", {"c.txt": "c\n"})
    rb.repo.git.merge("feature", "--no-ff", "-m", "Merge feature")

    commits = get_commits(str(rb.path))
    messages = [c["message"] for c in commits]
    assert messages[0] == "Merge feature"
    assert set(messages) == {"Merge feature", "main work", "feature work", "base"}
    by_msg = {c["message"]: c for c in commits}
    assert by_msg["feature work"]["files_changed"] == ["b.txt"]
    # The merge carries the diff of what the branch brought in (vs. main's side).
    assert by_msg["Merge feature"]["files_changed"] == ["b.txt"]
    assert "+b" in by_msg["Merge feature"]["diff_summary"]


def test_unicode_and_spaces_in_file_names(rb: RepoBuilder):
    rb.commit("i18n", {"docs/çalışma notları.md": "merhaba\n"})
    c = get_commits(str(rb.path))[0]
    assert c["files_changed"] == ["docs/çalışma notları.md"]
    assert "+merhaba" in c["diff_summary"]


def test_subdirectory_and_quoted_path_are_accepted(rb: RepoBuilder):
    rb.commit("Add", {"pkg/mod.py": "z = 3\n"})
    assert len(get_commits(f'"{rb.path / "pkg"}"')) == 1


def test_error_missing_folder(tmp_path: Path):
    with pytest.raises(RepoError, match="Folder not found"):
        get_commits(str(tmp_path / "nope"))


def test_error_file_instead_of_folder(tmp_path: Path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(RepoError, match="Not a folder"):
        get_commits(str(f))


def test_error_not_a_repo(tmp_path: Path):
    with pytest.raises(RepoError, match="Not a Git repository"):
        get_commits(str(tmp_path))


def test_error_empty_repo(rb: RepoBuilder):
    with pytest.raises(RepoError, match="no commits"):
        get_commits(str(rb.path))
