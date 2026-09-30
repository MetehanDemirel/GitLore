"""Git operations behind the commit explorer, diff view and editor.

Reading: commit list, files changed per commit, file contents before/after a commit.
Writing: only the working tree (edit files, stage them, make a *new* commit). Past commits are
never rewritten: no amend, rebase, reset or force of any kind.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import git

from src.git_parser import RepoError, open_repo

MAX_FILE_BYTES = 2_000_000       # larger files are shown as "too large" instead of in the editor
_US = "\x1f"
_RS = "\x1e"

LANGUAGE_BY_SUFFIX = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".json": "json", ".md": "markdown", ".html": "html",
    ".css": "css", ".scss": "scss", ".less": "less", ".yml": "yaml", ".yaml": "yaml", ".toml": "ini",
    ".ini": "ini", ".cfg": "ini", ".sh": "shell", ".bash": "shell", ".bat": "bat", ".ps1": "powershell",
    ".sql": "sql", ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".xml": "xml", ".dockerfile": "dockerfile", ".r": "r", ".lua": "lua", ".dart": "dart",
}


class GitOpError(Exception):
    """Raised with a user-friendly message; the API returns it as a 400."""


def language_for(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    if name == "dockerfile":
        return "dockerfile"
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(name).suffix, "plaintext")


# --------------------------------------------------------------------------- reading history
def list_commits(repo_path: str, query: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    """Commits reachable from HEAD, newest first. `query` filters message, author or hash (case-insensitive)."""
    repo = open_repo(repo_path)
    fmt = f"--format={_RS}%H{_US}%h{_US}%an{_US}%aI{_US}%P{_US}%s"
    out = repo.git.log("HEAD", fmt)
    commits = []
    q = query.strip().lower()
    for record in out.split(_RS)[1:]:
        hash_, short, author, date, parents, subject = record.rstrip("\n").split(_US, 5)
        if q and q not in subject.lower() and q not in author.lower() and not hash_.startswith(q):
            continue
        commits.append({"hash": hash_, "short_hash": short[:7], "author": author, "date": date,
                        "subject": subject, "parents": parents.split(), "is_merge": len(parents.split()) > 1})
    return commits[offset: offset + limit]


def commit_detail(repo_path: str, sha: str) -> dict:
    """Metadata and the files a commit changed (merges: compared with their first parent)."""
    repo = open_repo(repo_path)
    commit = _commit(repo, sha)
    parent = commit.parents[0] if commit.parents else None
    stats = commit.stats.files  # merges: compared with the first parent, like the diff
    if parent:
        changes = [({"A": "added", "D": "deleted", "R": "renamed"}.get(d.change_type, "modified"),
                    d.b_path or d.a_path, d.a_path) for d in parent.diff(commit)]
    else:  # root commit: everything in it was added
        changes = [("added", b.path, None) for b in commit.tree.traverse() if b.type == "blob"]
    files = []
    for status, path, old in changes:
        s = stats.get(path) or {}
        files.append({"path": path, "old_path": old if status == "renamed" else None, "status": status,
                      "additions": s.get("insertions"), "deletions": s.get("deletions"),
                      "language": language_for(path)})
    files.sort(key=lambda f: f["path"])
    return {"hash": commit.hexsha, "short_hash": commit.hexsha[:7], "author": commit.author.name,
            "email": commit.author.email, "date": commit.authored_datetime.isoformat(),
            "message": commit.message.strip(), "parents": [p.hexsha for p in commit.parents], "files": files}


def file_versions(repo_path: str, sha: str, path: str, old_path: str | None = None) -> dict:
    """File content before (first parent) and after the commit, for the side-by-side diff."""
    repo = open_repo(repo_path)
    commit = _commit(repo, sha)
    _check_rel_path(path)
    parent = commit.parents[0] if commit.parents else None
    original = _blob_text(parent, old_path or path) if parent else ""
    modified = _blob_text(commit, path)
    binary = original is None or modified is None
    return {"path": path, "language": language_for(path), "binary": binary,
            "original": "" if binary else original, "modified": "" if binary else modified}


# --------------------------------------------------------------------------- working tree
def status(repo_path: str) -> dict:
    """Branch and changed files in the working tree (like `git status`)."""
    repo = open_repo(repo_path)
    out = repo.git.status("--porcelain=v1", "-z", "--untracked-files=all")
    entries = [e for e in out.split("\0") if e]
    files, i = [], 0
    while i < len(entries):
        entry = entries[i]
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            i += 1  # the next entry is the original path
        files.append({"path": path, "code": code, "staged": code[0] not in " ?",
                      "untracked": code == "??", "language": language_for(path)})
        i += 1
    branch = None if repo.head.is_detached else repo.active_branch.name
    return {"branch": branch, "detached": repo.head.is_detached, "files": files,
            "busy": _operation_in_progress(repo)}


def read_file(repo_path: str, path: str) -> dict:
    """Working-tree content and the HEAD version of a file (for "edit, then see the diff")."""
    repo = open_repo(repo_path)
    target = _safe_path(repo, path)
    current = None
    if target.is_file():
        if target.stat().st_size > MAX_FILE_BYTES:
            raise GitOpError("This file is too large to open in the editor.")
        current = _decode(target.read_bytes())
    head = _blob_text(repo.head.commit, path) if repo.head.is_valid() else ""
    binary = (target.is_file() and current is None) or head is None
    return {"path": path, "language": language_for(path), "exists": target.is_file(), "binary": binary,
            "current": current or "", "head": head or ""}


def list_tree(repo_path: str) -> list[str]:
    """Tracked files plus untracked, not-ignored files (for "open a file to edit")."""
    repo = open_repo(repo_path)
    out = repo.git.ls_files("--cached", "--others", "--exclude-standard", "-z")
    return sorted({p for p in out.split("\0") if p})


def write_file(repo_path: str, path: str, content: str) -> None:
    repo = open_repo(repo_path)
    target = _safe_path(repo, path)
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise GitOpError("This file is too large to save from the editor.")
    target.parent.mkdir(parents=True, exist_ok=True)
    newline = "\r\n" if target.is_file() and b"\r\n" in target.read_bytes()[:65536] else "\n"
    target.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline=newline)


def commit(repo_path: str, message: str, paths: list[str]) -> dict:
    """Stage `paths` and create a new commit. Refuses anything that could rewrite or lose history."""
    repo = open_repo(repo_path)
    message = message.strip()
    if not message:
        raise GitOpError("Write a commit message first.")
    if not paths:
        raise GitOpError("Choose at least one changed file to commit.")
    if repo.head.is_detached:
        raise GitOpError("You are not on a branch (detached HEAD). Check out a branch in Git, then commit.")
    busy = _operation_in_progress(repo)
    if busy:
        raise GitOpError(f"A {busy} is in progress in this repository. Finish or abort it in Git first.")
    reader = repo.config_reader()
    if not (reader.get_value("user", "name", "") and reader.get_value("user", "email", "")):
        raise GitOpError('Git doesn\'t know who you are yet. Run: git config --global user.name "Your Name" '
                         'and git config --global user.email "you@example.com"')
    for p in paths:
        _safe_path(repo, p)
    try:
        repo.git.add("--all", "--", *paths)
        repo.git.commit("-m", message, "--", *paths)
    except git.GitCommandError as e:
        raise GitOpError(f"Git refused the commit: {(e.stderr or str(e)).strip()[:300]}") from None
    head = repo.head.commit
    return {"hash": head.hexsha, "short_hash": head.hexsha[:7], "subject": head.summary}


# --------------------------------------------------------------------------- helpers
def _commit(repo: git.Repo, sha: str) -> git.Commit:
    if not sha or not all(c in "0123456789abcdef" for c in sha.lower()):
        raise GitOpError("That doesn't look like a commit hash.")
    try:
        full = repo.git.rev_parse("--verify", "--quiet", f"{sha}^{{commit}}")
        return repo.commit(full)
    except (git.GitCommandError, git.BadName, ValueError):
        raise GitOpError(f"Commit {sha[:12]} was not found in this repository.") from None


def _blob_text(commit: git.Commit, path: str) -> str | None:
    """Text of `path` in `commit`; '' if the file didn't exist there, None if binary or too large."""
    try:
        blob = commit.tree / path
    except KeyError:
        return ""
    if blob.size > MAX_FILE_BYTES:
        return None
    return _decode(blob.data_stream.read())


def _decode(data: bytes) -> str | None:
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _check_rel_path(path: str) -> None:
    p = PurePosixPath(path.replace("\\", "/"))
    if not path or p.is_absolute() or ".." in p.parts or (p.parts and p.parts[0] == ".git") or ":" in path:
        raise GitOpError("That file path is not inside the repository.")


def _safe_path(repo: git.Repo, path: str) -> Path:
    """Resolve a repo-relative path, refusing anything outside the working tree or inside .git."""
    _check_rel_path(path)
    root = Path(repo.working_tree_dir).resolve()
    target = (root / path).resolve()
    if target != root and root not in target.parents:
        raise GitOpError("That file path is not inside the repository.")
    if ".git" in target.relative_to(root).parts:
        raise GitOpError("Files inside .git can't be edited.")
    return target


def _operation_in_progress(repo: git.Repo) -> str | None:
    gitdir = Path(repo.git_dir)
    for marker, name in (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
                         ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert"), ("BISECT_LOG", "bisect")):
        if (gitdir / marker).exists():
            return name
    return None


__all__ = ["GitOpError", "RepoError", "commit", "commit_detail", "file_versions", "language_for",
           "list_commits", "list_tree", "read_file", "status", "write_file"]
