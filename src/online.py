"""Online mode (opt-in): add public GitHub repositories by URL, keep them updated, and show the pull
requests, issues and releases behind the history.

No sign-in and no stored secrets. GitHub allows 60 anonymous API requests per hour; responses are
cached with ETags (a "not modified" answer doesn't count against the limit). Setting a GITHUB_TOKEN
environment variable raises the limit; GitLore never saves it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import git

from src import config, store

API = "https://api.github.com"
_GITHUB_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:[#?].*)?$", re.I)
_SHORT_RE = re.compile(r"^([\w.-]+)/([\w.-]+)$")
_ISSUE_RE = re.compile(r"(?<![\w/])#(\d{1,6})\b")
DEFAULT_DEPTH = 1000


class OnlineError(Exception):
    """Raised with a user-friendly message."""


# ============================================================================ URLs & cloning
def parse_repo(text: str) -> tuple[str, str]:
    """'github.com/microsoft/vscode', 'https://github.com/o/r.git' or 'o/r' -> ('o', 'r')."""
    text = text.strip()
    m = _GITHUB_RE.match(text) or _SHORT_RE.match(text)
    if not m:
        raise OnlineError("Enter a GitHub repository, for example github.com/microsoft/vscode.")
    return m.group(1), m.group(2)


def clone_path(owner: str, repo: str) -> Path:
    return config.DATA_DIR / "online" / owner.lower() / repo.lower()


def clone(owner: str, repo: str, depth: int, progress) -> Path:
    """Clone (shallow, newest `depth` commits) into data/online/<owner>/<repo>."""
    target = clone_path(owner, repo)
    if (target / ".git").is_dir():
        return target
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)  # an interrupted earlier clone
    target.parent.mkdir(parents=True, exist_ok=True)

    class _Progress(git.RemoteProgress):
        def update(self, op_code, cur_count, max_count=None, message=""):
            stage = "receiving" if op_code & self.RECEIVING else "resolving" if op_code & self.RESOLVING else "counting"
            progress(int(cur_count or 0), int(max_count or 0), stage)

    try:
        git.Repo.clone_from(f"https://github.com/{owner}/{repo}.git", target, progress=_Progress(),
                            multi_options=[f"--depth={int(depth)}"],  # passed explicitly: the depth kwarg was ignored
                            env={"GIT_TERMINAL_PROMPT": "0"})  # never prompt for a password
    except git.GitCommandError as e:
        shutil.rmtree(target, ignore_errors=True)
        err = (e.stderr or "").lower()
        if "not found" in err or "could not read username" in err or "authentication" in err:
            raise OnlineError(f"github.com/{owner}/{repo} wasn't found, or it's private. Only public repositories "
                              "can be added for now.") from None
        raise OnlineError("Cloning failed — check your internet connection and try again.") from None
    return target


def fetch(path: str, depth: int) -> dict:
    """Bring an online project up to date (read-only mirror: local edits are not kept)."""
    repo = git.Repo(path)
    before = repo.head.commit.hexsha
    branch = repo.active_branch.name
    try:
        repo.git.fetch("--depth", str(depth), "--tags", "origin", branch, env={"GIT_TERMINAL_PROMPT": "0"})
        repo.git.reset("--hard", f"origin/{branch}")
    except git.GitCommandError:
        raise OnlineError("Couldn't reach GitHub to check for updates. You can keep working offline.") from None
    after = repo.head.commit.hexsha
    new = int(repo.git.rev_list("--count", f"{before}..{after}")) if before != after else 0
    return {"updated": before != after, "new_commits": new, "head": after}


def is_online_project(project: dict) -> bool:
    return bool(project.get("remote_url"))


# ============================================================================ GitHub API
def _get(url: str, max_age_ok: bool = False):
    """GET a GitHub API URL, using the cache (ETag) to save rate limit. Returns parsed JSON."""
    cached = store.get_http(url)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"GitLore/{config.VERSION}",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cached and cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
            body = r.read().decode("utf-8")
            store.put_http(url, r.headers.get("ETag"), body)
            return json.loads(body)
    except urllib.error.HTTPError as e:
        if e.code == 304 and cached:
            return json.loads(cached["body"])
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
            if cached:
                return json.loads(cached["body"])
            raise OnlineError("GitHub's hourly limit for anonymous requests is used up. It resets within the "
                              "hour; setting a GITHUB_TOKEN environment variable raises the limit.") from None
        if e.code == 404:
            return None
        raise OnlineError(f"GitHub answered {e.code}. Try again later.") from None
    except (urllib.error.URLError, TimeoutError):
        if cached:
            return json.loads(cached["body"])
        raise OnlineError("You're offline or GitHub can't be reached right now.") from None


def repo_info(owner: str, repo: str) -> dict:
    d = _get(f"{API}/repos/{owner}/{repo}") or {}
    return {"full_name": d.get("full_name", f"{owner}/{repo}"), "description": d.get("description") or "",
            "stars": d.get("stargazers_count"), "forks": d.get("forks_count"), "open_issues": d.get("open_issues_count"),
            "language": d.get("language"), "default_branch": d.get("default_branch"), "url": d.get("html_url"),
            "license": (d.get("license") or {}).get("spdx_id"), "pushed_at": d.get("pushed_at")}


def _discussion_item(d: dict, kind: str) -> dict:
    body = (d.get("body") or "").strip()
    return {"kind": kind, "number": d.get("number"), "title": d.get("title", ""), "state": d.get("state"),
            "merged": bool(d.get("merged_at")), "url": d.get("html_url"), "author": (d.get("user") or {}).get("login"),
            "comments": d.get("comments"), "created_at": d.get("created_at"), "body": body[:1200]}


def discussions(owner: str, repo: str, sha: str, message: str) -> list[dict]:
    """Pull requests that contain the commit, plus issues/PRs its message references (#123)."""
    items: dict[int, dict] = {}
    for pr in _get(f"{API}/repos/{owner}/{repo}/commits/{sha}/pulls") or []:
        items[pr["number"]] = _discussion_item(pr, "pull")
    for num in dict.fromkeys(_ISSUE_RE.findall(message)):
        n = int(num)
        if n in items or len(items) >= 6:
            continue
        d = _get(f"{API}/repos/{owner}/{repo}/issues/{n}")
        if d:
            items[n] = _discussion_item(d, "pull" if "pull_request" in d else "issue")
    for item in list(items.values())[:3]:
        if item["comments"]:
            comments = _get(f"{API}/repos/{owner}/{repo}/issues/{item['number']}/comments?per_page=5") or []
            item["top_comments"] = [{"author": (c.get("user") or {}).get("login"), "body": (c.get("body") or "")[:500]}
                                    for c in comments[:5]]
    return list(items.values())


def releases(owner: str, repo: str) -> list[dict]:
    return [{"tag": r.get("tag_name"), "name": r.get("name") or r.get("tag_name"), "date": r.get("published_at"),
             "body": (r.get("body") or "")[:2000], "url": r.get("html_url"), "prerelease": r.get("prerelease")}
            for r in (_get(f"{API}/repos/{owner}/{repo}/releases?per_page=30") or [])]


def owner_repo(project: dict) -> tuple[str, str] | None:
    url = project.get("remote_url")
    if not url:
        return None
    try:
        return parse_repo(url)
    except OnlineError:
        return None
