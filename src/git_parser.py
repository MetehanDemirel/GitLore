"""Extract structured commit data from a local Git repository.

All history is read with a single streamed `git log -p` call (via GitPython) rather than
per-commit API calls, which would spawn one git process per commit and be very slow on
large repos. Diffs are truncated while streaming, so memory stays bounded.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypedDict

# Don't let a missing `git` binary crash the import; we report it nicely at call time.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
import git  # noqa: E402

from src import config  # noqa: E402

# ASCII record/unit separators: can't appear in normal commit text, so parsing is unambiguous.
_RS = "\x1e"
_US = "\x1f"
_LOG_FORMAT = f"--format={_RS}%H{_US}%an{_US}%aI{_US}%B{_US}"


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


def open_repo(repo_path: str) -> git.Repo:
    """Open a repository (a subfolder of one is fine), raising RepoError with a readable message."""
    path = Path(repo_path.strip().strip('"')).expanduser()
    if not path.exists():
        raise RepoError(f"Folder not found: {path}")
    if not path.is_dir():
        raise RepoError(f"Not a folder: {path}")
    try:
        repo = git.Repo(path, search_parent_directories=True)
        repo.git.version()
    except git.InvalidGitRepositoryError:
        raise RepoError(f"Not a Git repository: {path}") from None
    except git.GitCommandNotFound:
        raise RepoError("Git is not installed or not on PATH. Install it from https://git-scm.com") from None
    if repo.bare:
        raise RepoError("Bare repositories aren't supported; point GitLore at a normal checkout.")
    if not repo.head.is_valid():
        raise RepoError("This repository has no commits yet.")
    return repo


_REMOTE_RE = re.compile(
    r"^(?:https?://(?:[^@/]+@)?|ssh://git@|git@)(?P<host>github\.com|gitlab\.com)[:/](?P<path>.+?)(?:\.git)?/?$"
)


def commit_url_base(repo_path: str) -> str | None:
    """Web URL prefix for commits (…/commit/<hash>) if `origin` is on GitHub or GitLab, else None."""
    try:
        url = open_repo(repo_path).remotes.origin.url
    except (RepoError, AttributeError, ValueError):
        return None
    m = _REMOTE_RE.match(url.strip())
    if not m:
        return None
    sep = "/-/commit/" if m["host"] == "gitlab.com" else "/commit/"
    return f"https://{m['host']}/{m['path']}{sep}"


def get_commits(repo_path: str, max_count: int = config.DEFAULT_COMMIT_COUNT) -> list[Commit]:
    """Return up to `max_count` commits reachable from HEAD, newest first."""
    repo = open_repo(repo_path)
    # c=... is a global git option (git -c core.quotepath=off log ...): keep non-ASCII names readable.
    proc = repo.git(c="core.quotepath=off").log(
        "HEAD",
        f"--max-count={max(1, int(max_count))}",
        _LOG_FORMAT,
        "--patch",
        "--unified=0",       # changed lines only; context lines cost tokens and add little
        "--no-color",
        "--no-ext-diff",
        "--no-renames",      # guarantees a/<path> == b/<path> in diff headers
        # Merge commits get the diff of everything they brought in: on PR-based repos the merge
        # message (PR title) plus the PR's full diff is often the best "why" in the history.
        "--diff-merges=first-parent",
        as_process=True,
    )
    try:
        lines = (raw.decode("utf-8", errors="replace").rstrip("\r\n") for raw in proc.stdout)
        commits = list(_parse_log(lines))
    finally:
        proc.stdout.close()
        proc.wait()
    return commits


def _parse_log(lines: Iterable[str]) -> Iterator[Commit]:
    """Parse `git log` output made with _LOG_FORMAT + --patch.

    Each commit starts with RS; its header (hash, author, date, multi-line message) ends at the
    4th US. Everything after that, until the next RS, is the commit's patch.
    """
    header: list[str] = []
    separators = 0
    builder: _CommitBuilder | None = None

    for line in lines:
        if line.startswith(_RS):
            if builder:
                yield builder.build()
            builder = None
            line = line[1:]
            header, separators = [], 0
        elif builder:
            builder.add_diff_line(line)
            continue

        header.append(line)
        separators += line.count(_US)
        if separators >= 4:
            hash_, author, date, message, _ = "\n".join(header).split(_US, 4)
            builder = _CommitBuilder(hash_, author, date, message.strip())

    if builder:
        yield builder.build()


class _CommitBuilder:
    def __init__(self, hash_: str, author: str, date: str, message: str) -> None:
        self.hash, self.author, self.date, self.message = hash_, author, date, message
        self.files: list[str] = []
        self.parts: list[str] = []
        self.chars = 0
        self.truncated = False
        self.skip_current_file = False

    def add_diff_line(self, line: str) -> None:
        if line.startswith("diff --git a/"):
            # "diff --git a/<p> b/<p>" with identical paths (--no-renames): take the first half.
            rest = line[len("diff --git a/"):]
            path = rest[: (len(rest) - 3) // 2]
            self.files.append(path)
            self.skip_current_file = _is_noisy(path)
            self._emit(f"\n### {path}" + (" (diff omitted: generated/lock file)" if self.skip_current_file else ""))
        elif line.startswith("Binary files "):
            self._emit("(binary file changed)")
        elif line.startswith(("new file mode", "deleted file mode")):
            self._emit(f"({line.split(' mode')[0]})")
        elif self.skip_current_file or line.startswith(("index ", "--- ", "+++ ", "old mode", "new mode")):
            return
        elif line.startswith(("@@", "+", "-")):
            self._emit(line)

    def _emit(self, text: str) -> None:
        if self.truncated:
            return
        if self.chars + len(text) + 1 > config.MAX_DIFF_CHARS_PER_COMMIT:
            self.parts.append("… (diff truncated)")
            self.truncated = True
            return
        self.parts.append(text)
        self.chars += len(text) + 1

    def build(self) -> Commit:
        return Commit(
            hash=self.hash,
            short_hash=self.hash[:7],
            author=self.author,
            date=self.date,
            message=self.message,
            files_changed=self.files[: config.MAX_FILES_LISTED],
            diff_summary="\n".join(self.parts).strip(),
        )


def _is_noisy(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in config.NOISY_DIFF_FILES or name.endswith(config.NOISY_DIFF_SUFFIXES)
