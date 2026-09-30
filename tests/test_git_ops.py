from __future__ import annotations

from pathlib import Path

import git
import pytest

from src import git_ops
from src.git_ops import GitOpError


@pytest.fixture
def repo(rb):
    rb.commit("Add app", {"app.py": "print('hi')\n", "logo.png": b"\x89PNG\x00\x01"})
    rb.commit("Change greeting\n\nFriendlier.", {"app.py": "print('hello')\n", "notes.md": "# Notes\n"})
    return rb


def test_list_commits_and_search(repo):
    commits = git_ops.list_commits(str(repo.path))
    assert [c["subject"] for c in commits] == ["Change greeting", "Add app"]
    assert commits[0]["author"] == "Ada Lovelace" and len(commits[0]["short_hash"]) == 7
    assert [c["subject"] for c in git_ops.list_commits(str(repo.path), query="GREETING")] == ["Change greeting"]
    assert git_ops.list_commits(str(repo.path), query=commits[1]["hash"][:8])[0]["subject"] == "Add app"
    assert len(git_ops.list_commits(str(repo.path), limit=1, offset=1)) == 1


def test_commit_detail_lists_changed_files(repo):
    head = git_ops.list_commits(str(repo.path))[0]["hash"]
    detail = git_ops.commit_detail(str(repo.path), head)
    assert detail["message"] == "Change greeting\n\nFriendlier."
    by_path = {f["path"]: f for f in detail["files"]}
    assert by_path["app.py"]["status"] == "modified" and by_path["app.py"]["language"] == "python"
    assert by_path["notes.md"]["status"] == "added"
    assert by_path["app.py"]["additions"] == 1 and by_path["app.py"]["deletions"] == 1


def test_root_commit_shows_everything_as_added(repo):
    root = git_ops.list_commits(str(repo.path))[-1]["hash"]
    files = git_ops.commit_detail(str(repo.path), root)["files"]
    assert {f["path"]: f["status"] for f in files} == {"app.py": "added", "logo.png": "added"}


def test_file_versions_for_the_diff(repo):
    head, root = [c["hash"] for c in git_ops.list_commits(str(repo.path))]
    v = git_ops.file_versions(str(repo.path), head, "app.py")
    assert (v["original"], v["modified"], v["binary"]) == ("print('hi')\n", "print('hello')\n", False)
    assert git_ops.file_versions(str(repo.path), head, "notes.md")["original"] == ""
    assert git_ops.file_versions(str(repo.path), root, "logo.png")["binary"] is True


def test_merge_commit_is_compared_with_first_parent(rb):
    rb.commit("base", {"a.txt": "a\n"})
    rb.repo.git.checkout("-b", "feature")
    rb.commit("feature", {"b.txt": "b\n"})
    rb.repo.git.checkout("main")
    rb.commit("main work", {"c.txt": "c\n"})
    rb.repo.git.merge("feature", "--no-ff", "-m", "Merge feature")
    merge = git_ops.list_commits(str(rb.path))[0]
    assert merge["is_merge"]
    assert [f["path"] for f in git_ops.commit_detail(str(rb.path), merge["hash"])["files"]] == ["b.txt"]


def test_bad_commit_hash_gives_friendly_error(repo):
    for bad in ["zzz", "", "HEAD~1; rm -rf /", "0" * 40]:
        with pytest.raises(GitOpError):
            git_ops.commit_detail(str(repo.path), bad)


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "C:/Windows/win.ini", ".git/config",
                                  "sub/../../outside.txt", ""])
def test_paths_outside_the_repo_are_refused(repo, path):
    with pytest.raises(GitOpError):
        git_ops.write_file(str(repo.path), path, "x")
    with pytest.raises(GitOpError):
        git_ops.read_file(str(repo.path), path)


def test_edit_status_and_commit(repo):
    path = str(repo.path)
    before = git_ops.read_file(path, "app.py")
    assert before["current"] == before["head"] == "print('hello')\n"

    git_ops.write_file(path, "app.py", "print('hello, world')\n")
    git_ops.write_file(path, "new/feature.py", "x = 1\n")
    st = git_ops.status(path)
    assert st["branch"] == "main" and not st["detached"] and st["busy"] is None
    assert {f["path"]: f["code"] for f in st["files"]} == {"app.py": " M", "new/feature.py": "??"}
    assert git_ops.read_file(path, "app.py")["head"] == "print('hello')\n"

    result = git_ops.commit(path, "Say hello to the world", ["app.py"])
    assert result["subject"] == "Say hello to the world"
    head = repo.repo.head.commit
    assert head.hexsha == result["hash"] and head.author.name == "Ada Lovelace"
    assert [f["path"] for f in git_ops.status(path)["files"]] == ["new/feature.py"], "only the chosen file was committed"
    assert "new/feature.py" in git_ops.list_tree(path)


def test_commit_can_record_a_deletion(repo):
    (repo.path / "notes.md").unlink()
    git_ops.commit(str(repo.path), "Remove notes", ["notes.md"])
    assert "notes.md" not in repo.repo.git.ls_files()


def test_commit_keeps_crlf_files_crlf(repo):
    (repo.path / "win.txt").write_bytes(b"a\r\nb\r\n")
    git_ops.write_file(str(repo.path), "win.txt", "a\nb\nc\n")
    assert (repo.path / "win.txt").read_bytes() == b"a\r\nb\r\nc\r\n"


def test_commit_guards(repo):
    path = str(repo.path)
    git_ops.write_file(path, "app.py", "changed\n")
    with pytest.raises(GitOpError, match="message"):
        git_ops.commit(path, "   ", ["app.py"])
    with pytest.raises(GitOpError, match="at least one"):
        git_ops.commit(path, "msg", [])

    (Path(repo.repo.git_dir) / "MERGE_HEAD").write_text(repo.repo.head.commit.hexsha)
    with pytest.raises(GitOpError, match="merge is in progress"):
        git_ops.commit(path, "msg", ["app.py"])
    (Path(repo.repo.git_dir) / "MERGE_HEAD").unlink()

    repo.repo.git.checkout("--detach")
    with pytest.raises(GitOpError, match="detached"):
        git_ops.commit(path, "msg", ["app.py"])


def test_commit_without_identity_explains_how_to_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "empty-global"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    r = git.Repo.init(tmp_path / "r", initial_branch="main")
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Temp")
        cw.set_value("user", "email", "t@example.com")
    (tmp_path / "r" / "a.txt").write_text("a\n")
    r.git.add("a.txt")
    r.git.commit("-m", "init")
    with r.config_writer() as cw:
        cw.remove_section("user")
    git_ops.write_file(str(tmp_path / "r"), "a.txt", "b\n")
    with pytest.raises(GitOpError, match="user.name"):
        git_ops.commit(str(tmp_path / "r"), "msg", ["a.txt"])


def test_language_detection():
    assert git_ops.language_for("src/app.ts") == "typescript"
    assert git_ops.language_for("Dockerfile") == "dockerfile"
    assert git_ops.language_for("LICENSE") == "plaintext"
