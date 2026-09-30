"""Repository insights computed straight from Git — no model, so they are instant.

One `git log --numstat` pass feeds everything: commit categories, contributors, hot files, a commit
heatmap, monthly activity, releases, branches and comparisons. Results are cached per repository
state (HEAD + refs), so switching views is free.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import PurePosixPath

from src.git_ops import GitOpError
from src.git_parser import open_repo

_RS, _US = "\x1e", "\x1f"

CATEGORIES = ["feature", "bugfix", "security", "performance", "refactor", "docs", "tests", "dependencies",
              "ci", "style", "revert", "merge", "chore"]

_CONVENTIONAL = {
    "feat": "feature", "feature": "feature", "fix": "bugfix", "bugfix": "bugfix", "hotfix": "bugfix",
    "perf": "performance", "refactor": "refactor", "docs": "docs", "doc": "docs", "test": "tests",
    "tests": "tests", "build": "dependencies", "deps": "dependencies", "ci": "ci", "style": "style",
    "chore": "chore", "security": "security", "sec": "security", "revert": "revert", "wip": "feature",
}
_CONVENTIONAL_RE = re.compile(r"^(\w+)(\(([^)]*)\))?(!)?:\s", re.I)

# Checked in order; the first match decides the primary category. Word boundaries keep "prefix" from
# matching "fix" and "latest" from matching "test".
_KEYWORDS = [
    ("revert", r"^revert\b"),
    ("merge", r"^merge (pull request|branch|remote-tracking)\b"),
    ("security", r"\b(security|vulnerab\w*|injection|xss|csrf|cve-\d+|exploit|rate[- ]limit\w*|brute[- ]?force|"
                 r"password|pbkdf2|argon2|expired tokens?|authentication|auth bypass|sanitiz\w*|escape user input)\b"),
    ("performance", r"\b(perf|performance|faster|speed(s|ed)? up|slow|latency|optimi[sz]\w*|cach(e|ing)|"
                    r"index(es)? on|n\+1|memory usage|throughput)\b"),
    ("bugfix", r"\b(fix(es|ed)?|bug|crash\w*|regression|broken|wrong|incorrect|typo|issue #?\d+|hotfix|"
               r"handle (empty|missing|invalid))\b"),
    ("refactor", r"\b(refactor\w*|restructur\w*|split (into|up)|extract\w*|rename\w*|simplif\w*|clean ?up|"
                 r"move (code|storage|files)|reorganiz\w*)\b"),
    ("docs", r"\b(docs?|documentation|readme|faq|guide|changelog|comment(s)?)\b"),
    ("tests", r"\b(tests?|testing|coverage|pytest|unit test|regression test)\b"),
    ("dependencies", r"\b(bump|upgrade|update dependencies|dependency|dependencies|requirements|pin)\b"),
    ("ci", r"\b(ci|github actions|workflow|pipeline)\b"),
    ("style", r"\b(format(ted|ting)?|black|isort|lint\w*|whitespace|sort imports)\b"),
    ("feature", r"\b(add(s|ed)?|implement\w*|support(s)?|introduc\w*|new|allow\w*|enable\w*|bring back)\b"),
]
_KEYWORDS = [(cat, re.compile(rx, re.I)) for cat, rx in _KEYWORDS]

DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc")
LARGE_LINES = 400        # a commit touching this many lines, or
LARGE_FILES = 12         # this many files, is flagged as a large change

_cache: dict[str, tuple[str, dict]] = {}


# ============================================================================ categorization
def categorize(subject: str, body: str = "", files: list[str] | None = None, lines: int = 0,
               parents: int = 1) -> dict:
    """Primary category, all matching categories, and whether it's a large change. Heuristic by design."""
    files = files or []
    text = subject.strip()
    found: list[str] = []
    m = _CONVENTIONAL_RE.match(text)
    if m:
        mapped = _CONVENTIONAL.get(m.group(1).lower())
        scope = (m.group(3) or "").lower()
        if mapped == "chore" and scope in ("deps", "dependencies"):
            mapped = "dependencies"
        if mapped:
            found.append(mapped)
        text = text[m.end():]
    if parents > 1:
        found.append("merge")
    for cat, rx in _KEYWORDS:
        if rx.search(text) or (cat == "security" and rx.search(body)):
            found.append(cat)
    only = None
    if files and all(f.endswith(DOC_SUFFIXES) or f.startswith("docs/") for f in files):
        only = "docs"
    elif files and all(PurePosixPath(f).name.startswith(("test", "conftest")) or "/tests/" in f"/{f}" for f in files):
        only = "tests"
    if only:
        found.append(only)
    unique = list(dict.fromkeys(found)) or ["chore"]
    if m and unique[0] != "chore":
        primary = unique[0]                       # an explicit "fix:", "perf:" … prefix is the author's own label
    elif only:
        primary = only                            # touching only tests/docs says more than words in the message
    elif "security" in unique:
        primary = "security"                      # otherwise security outranks other keywords
    else:
        primary = unique[0]
    breaking = "BREAKING CHANGE" in body or (m is not None and m.group(4) == "!")
    large = breaking or lines >= LARGE_LINES or len(files) >= LARGE_FILES
    return {"primary": primary, "all": unique, "large": large, "breaking": breaking}


# ============================================================================ the one pass over history
def _load(repo_path: str) -> dict:
    repo = open_repo(repo_path)
    key = repo.head.commit.hexsha + "|" + ",".join(sorted(f"{r.path}={r.commit.hexsha}" for r in repo.refs
                                                          if not r.path.startswith("refs/remotes/")))
    cached = _cache.get(repo.working_tree_dir)
    if cached and cached[0] == key:
        return cached[1]
    fmt = f"--format={_RS}%H{_US}%an{_US}%ae{_US}%aI{_US}%P{_US}%s{_US}%b{_US}"
    out = repo.git(c="core.quotepath=off").log("HEAD", fmt, "--numstat", "--no-renames",
                                               "--diff-merges=first-parent")
    commits = []
    for record in out.split(_RS)[1:]:
        hash_, author, email, date, parents, subject, body, rest = record.split(_US, 7)
        files = []
        for line in rest.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                add, dele, path = parts
                files.append((path, int(add) if add.isdigit() else 0, int(dele) if dele.isdigit() else 0))
        n_parents = len(parents.split())
        lines = sum(a + d for _, a, d in files)
        cat = categorize(subject, body, [f for f, _, _ in files], lines, n_parents)
        commits.append({"hash": hash_, "short_hash": hash_[:7], "author": author, "email": email, "date": date,
                        "subject": subject, "body": body.strip(), "parents": n_parents, "files": files,
                        "additions": sum(a for _, a, _ in files), "deletions": sum(d for _, _, d in files),
                        "category": cat["primary"], "categories": cat["all"], "large": cat["large"],
                        "breaking": cat["breaking"]})
    data = {"commits": commits, "by_hash": {c["hash"]: c for c in commits}}
    _cache[repo.working_tree_dir] = (key, data)
    return data


def commit_categories(repo_path: str) -> dict[str, dict]:
    """hash -> {category, large} for the commit timeline's chips."""
    return {c["hash"]: {"category": c["category"], "large": c["large"]} for c in _load(repo_path)["commits"]}


# ============================================================================ views
def overview(repo_path: str) -> dict:
    commits = _load(repo_path)["commits"]
    if not commits:
        return {"commits": 0}
    cats = Counter(c["category"] for c in commits)
    authors = Counter(c["author"] for c in commits)
    return {
        "commits": len(commits),
        "contributors": len(authors),
        "first": commits[-1]["date"], "last": commits[0]["date"],
        "categories": [{"category": k, "count": v} for k, v in cats.most_common()],
        "large": [_brief(c) for c in commits if c["large"]][:12],
        "files": len({f for c in commits for f, _, _ in c["files"]}),
    }


def heatmap(repo_path: str) -> dict:
    """Commits per day (local date of the author)."""
    days = Counter(c["date"][:10] for c in _load(repo_path)["commits"])
    return {"days": dict(sorted(days.items())), "max": max(days.values(), default=0)}


def activity(repo_path: str) -> list[dict]:
    """Commits per month, split by category."""
    months: dict[str, Counter] = defaultdict(Counter)
    for c in _load(repo_path)["commits"]:
        months[c["date"][:7]][c["category"]] += 1
    return [{"month": m, "total": sum(cs.values()), "categories": dict(cs)} for m, cs in sorted(months.items())]


def contributors(repo_path: str) -> list[dict]:
    per: dict[str, dict] = {}
    for c in _load(repo_path)["commits"]:
        p = per.setdefault(c["author"], {"name": c["author"], "email": c["email"], "commits": 0, "additions": 0,
                                         "deletions": 0, "first": c["date"], "last": c["date"],
                                         "categories": Counter(), "areas": Counter()})
        p["commits"] += 1
        p["additions"] += c["additions"]
        p["deletions"] += c["deletions"]
        p["first"] = min(p["first"], c["date"])
        p["last"] = max(p["last"], c["date"])
        p["categories"][c["category"]] += 1
        for f, _, _ in c["files"]:
            p["areas"][_area(f)] += 1
    out = []
    for p in sorted(per.values(), key=lambda x: -x["commits"]):
        out.append({**p, "categories": dict(p["categories"].most_common()),
                    "areas": [a for a, _ in p["areas"].most_common(4)]})
    return out


def profile(repo_path: str, author: str) -> dict:
    commits = [c for c in _load(repo_path)["commits"] if c["author"] == author]
    if not commits:
        raise GitOpError(f"No commits by {author} in this repository.")
    summary = next(p for p in contributors(repo_path) if p["name"] == author)
    files = Counter(f for c in commits for f, _, _ in c["files"])
    months = Counter(c["date"][:7] for c in commits)
    return {**summary, "top_files": [{"path": f, "commits": n} for f, n in files.most_common(8)],
            "months": dict(sorted(months.items())), "recent": [_brief(c) for c in commits[:10]],
            "large": [_brief(c) for c in commits if c["large"]][:6]}


def hot_files(repo_path: str, limit: int = 25) -> list[dict]:
    """Files changed most often (churn), ignoring merges so pull requests aren't counted twice."""
    stats: dict[str, dict] = {}
    for c in _load(repo_path)["commits"]:
        if c["parents"] > 1:
            continue
        for f, a, d in c["files"]:
            s = stats.setdefault(f, {"path": f, "commits": 0, "lines": 0, "authors": set(), "last": c["date"]})
            s["commits"] += 1
            s["lines"] += a + d
            s["authors"].add(c["author"])
            s["last"] = max(s["last"], c["date"])
    rows = sorted(stats.values(), key=lambda s: (-s["commits"], -s["lines"]))[:limit]
    return [{**r, "authors": sorted(r["authors"])} for r in rows]


def releases(repo_path: str) -> list[dict]:
    """Tags, newest first, with what changed since the previous tag."""
    repo = open_repo(repo_path)
    data = _load(repo_path)
    tags = []
    for t in repo.tags:
        try:
            commit = t.commit
        except ValueError:
            continue
        tag_obj = t.tag
        tags.append({"name": t.name, "hash": commit.hexsha,
                     "date": (datetime.fromtimestamp(tag_obj.tagged_date).astimezone().isoformat() if tag_obj
                              else commit.committed_datetime.isoformat()),
                     "message": (tag_obj.message.strip() if tag_obj else ""),
                     "tagger": (tag_obj.tagger.name if tag_obj and tag_obj.tagger else commit.author.name)})
    tags.sort(key=lambda t: t["date"])
    out = []
    for i, tag in enumerate(tags):
        rng = f"{tags[i - 1]['name']}..{tag['name']}" if i else tag["name"]
        hashes = repo.git.rev_list(rng).split()
        cs = [data["by_hash"][h] for h in hashes if h in data["by_hash"]]
        out.append({**tag, "previous": tags[i - 1]["name"] if i else None, "commit_count": len(cs),
                    "categories": dict(Counter(c["category"] for c in cs).most_common()),
                    "contributors": [a for a, _ in Counter(c["author"] for c in cs).most_common()],
                    "highlights": [_brief(c) for c in cs if c["category"] in ("feature", "security", "performance")
                                   or c["large"]][:8]})
    return list(reversed(out))


def branches(repo_path: str) -> list[dict]:
    repo = open_repo(repo_path)
    base = repo.active_branch.name if not repo.head.is_detached else "HEAD"
    out = []
    for b in repo.branches:
        ahead, behind = (0, 0)
        if b.name != base:
            left, right = repo.git.rev_list("--left-right", "--count", f"{base}...{b.name}").split()
            behind, ahead = int(left), int(right)
        c = b.commit
        out.append({"name": b.name, "current": b.name == base, "hash": c.hexsha, "subject": c.summary,
                    "author": c.author.name, "date": c.committed_datetime.isoformat(), "ahead": ahead,
                    "behind": behind, "merged": b.name != base and ahead == 0})
    return sorted(out, key=lambda b: (not b["current"], b["merged"], b["date"]), reverse=False)


def compare(repo_path: str, base: str, head: str) -> dict:
    """What `head` has that `base` doesn't: commits, files and a category summary."""
    repo = open_repo(repo_path)
    for ref in (base, head):
        if not ref or ref.startswith("-") or not re.fullmatch(r"[\w./@^~-]+", ref):
            raise GitOpError(f"“{ref}” is not a valid branch, tag or commit.")
        try:
            repo.git.rev_parse("--verify", "--quiet", f"{ref}^{{commit}}")
        except Exception:
            raise GitOpError(f"“{ref}” was not found in this repository.") from None
    data = _load(repo_path)
    hashes = repo.git.rev_list(f"{base}..{head}").split()
    cs = [data["by_hash"].get(h) or {"hash": h, "short_hash": h[:7], "subject": repo.commit(h).summary,
                                      "author": repo.commit(h).author.name, "date": repo.commit(h).committed_datetime.isoformat(),
                                      "category": "chore", "large": False} for h in hashes]
    files = []
    for line in repo.git.diff("--numstat", "--no-renames", base, head).splitlines():
        add, dele, path = line.split("\t")
        files.append({"path": path, "additions": int(add) if add.isdigit() else 0,
                      "deletions": int(dele) if dele.isdigit() else 0})
    behind = len(repo.git.rev_list(f"{head}..{base}").split())
    return {"base": base, "head": head, "ahead": len(cs), "behind": behind,
            "commits": [_brief(c) for c in cs][:300], "files": files,
            "categories": dict(Counter(c["category"] for c in cs).most_common())}


def search(repo_path: str, query: str, limit: int = 200) -> dict:
    """Advanced search: `author:ada path:auth type:security since:2025-06 until:2025-12 release:v2.0.0 words`."""
    filters, words = parse_query(query)
    repo = open_repo(repo_path)
    data = _load(repo_path)
    allowed: set[str] | None = None
    if "release" in filters:
        rel = next((r for r in releases(repo_path) if r["name"] == filters["release"]), None)
        if not rel:
            raise GitOpError(f"No release named “{filters['release']}”.")
        rng = f"{rel['previous']}..{rel['name']}" if rel["previous"] else rel["name"]
        allowed = set(repo.git.rev_list(rng).split())
    out = []
    for c in data["commits"]:
        if allowed is not None and c["hash"] not in allowed:
            continue
        if "author" in filters and filters["author"].lower() not in (c["author"] + " " + c["email"]).lower():
            continue
        if "type" in filters and filters["type"] != c["category"]:
            continue
        if "path" in filters and not any(filters["path"].lower() in f.lower() for f, _, _ in c["files"]):
            continue
        if "since" in filters and c["date"][:len(filters["since"])] < filters["since"]:
            continue
        if "until" in filters and c["date"][:len(filters["until"])] > filters["until"]:
            continue
        if filters.get("large") and not c["large"]:
            continue
        text = f"{c['subject']}\n{c['body']}".lower()
        if words and not all(w.lower() in text or c["hash"].startswith(w.lower()) for w in words):
            continue
        out.append(_brief(c))
        if len(out) >= limit:
            break
    return {"filters": filters, "words": words, "results": out}


_FILTER_RE = re.compile(r'(\w+):("([^"]*)"|(\S+))')
FILTER_ALIASES = {"author": "author", "by": "author", "path": "path", "file": "path", "type": "type",
                  "category": "type", "since": "since", "after": "since", "until": "until", "before": "until",
                  "release": "release", "tag": "release", "is": "is"}
TYPE_ALIASES = {"fix": "bugfix", "bug": "bugfix", "bugs": "bugfix", "feat": "feature", "features": "feature",
                "perf": "performance", "sec": "security", "deps": "dependencies", "test": "tests", "doc": "docs"}


def parse_query(query: str) -> tuple[dict, list[str]]:
    filters: dict = {}
    for m in _FILTER_RE.finditer(query):
        key = FILTER_ALIASES.get(m.group(1).lower())
        value = m.group(3) if m.group(3) is not None else m.group(4)
        if key == "is" and value.lower() == "large":
            filters["large"] = True
        elif key == "type":
            filters["type"] = TYPE_ALIASES.get(value.lower(), value.lower())
        elif key:
            filters[key] = value
    rest = _FILTER_RE.sub(" ", query)
    return filters, [w for w in rest.split() if w]


def blame(repo_path: str, path: str) -> dict:
    """Who wrote the current lines of a file ("who knows this code?")."""
    from src.git_ops import _check_rel_path
    _check_rel_path(path)
    repo = open_repo(repo_path)
    try:
        out = repo.git.blame("--line-porcelain", "HEAD", "--", path)
    except Exception:
        raise GitOpError(f"{path} has no history at HEAD.") from None
    lines: Counter = Counter()
    last: dict[str, str] = {}
    author = None
    for line in out.splitlines():
        if line.startswith("author "):
            author = line[7:]
        elif line.startswith("author-time ") and author:
            ts = datetime.fromtimestamp(int(line[12:])).astimezone().isoformat()
            last[author] = max(last.get(author, ts), ts)
        elif line.startswith("\t") and author:
            lines[author] += 1
    total = sum(lines.values()) or 1
    return {"path": path, "lines": total,
            "authors": [{"name": a, "lines": n, "share": round(n / total, 3), "last": last.get(a)}
                        for a, n in lines.most_common()]}


# ============================================================================ helpers
def _area(path: str) -> str:
    parts = PurePosixPath(path).parts
    return "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if len(parts) > 1 else "(root)")


def _brief(c: dict) -> dict:
    return {"hash": c["hash"], "short_hash": c["short_hash"], "subject": c["subject"], "author": c["author"],
            "date": c["date"], "category": c.get("category", "chore"), "large": c.get("large", False),
            "additions": c.get("additions"), "deletions": c.get("deletions")}


_ISSUE_RE = re.compile(r"(?<![\w/])#(\d{1,6})\b")
_REVERT_RE = re.compile(r'^Revert "(.+)"', re.I)
_REVERTS_HASH_RE = re.compile(r"This reverts commit ([0-9a-f]{7,40})")


def related(repo_path: str, hashes: list[str], limit: int = 4) -> list[str]:
    """Commits that explain the given ones: the same issue/PR number, the commit a revert undid, and
    later commits that revert or redo it. Used to dig for *why*, not just what."""
    data = _load(repo_path)
    by_hash, commits = data["by_hash"], data["commits"]
    found: list[str] = []
    for h in hashes:
        c = by_hash.get(h)
        if not c:
            continue
        text = f"{c['subject']}\n{c['body']}"
        refs = set(_ISSUE_RE.findall(text))
        m = _REVERT_RE.match(c["subject"])
        undone = m.group(1) if m else None
        rh = _REVERTS_HASH_RE.search(c["body"])
        for other in commits:
            if other["hash"] == h or other["hash"] in found or other["hash"] in hashes:
                continue
            other_text = f"{other['subject']}\n{other['body']}"
            if (refs and refs & set(_ISSUE_RE.findall(other_text))) \
                    or (undone and other["subject"] == undone) \
                    or (rh and other["hash"].startswith(rh.group(1))) \
                    or other["subject"] == f'Revert "{c["subject"]}"':
                found.append(other["hash"])
            if len(found) >= limit:
                return found
    return found


def commits_since(repo_path: str, since_iso: str) -> list[dict]:
    return [c for c in _load(repo_path)["commits"] if c["date"] >= since_iso]


def all_commits(repo_path: str) -> list[dict]:
    return _load(repo_path)["commits"]
