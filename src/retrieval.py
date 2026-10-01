"""Pick the commits an answer is based on.

Meaning-based search alone is weak at "filter" questions a small model can't fix later: who did X,
what's the latest, security fixes, what changed in v1.2, how did auth.py evolve. So the question is
read for authors, files, releases, categories and recency first; the matching commits (via the
Insights index, no AI) go ahead of the meaning-based hits.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from pathlib import PurePosixPath

from src import chat_engine, config, insights, vector_store
from src.git_parser import Commit, get_commits

SEMANTIC_TOP_K = 8
FILTERED_MAX = 10

# Words that point at a category (the question's language is usually English; the model translates).
_CATEGORY_WORDS = [
    ("security", r"secur|vulnerab|exploit|injection|cve|xss|csrf"),
    ("bugfix", r"\bbugs?\b|\bfix(es|ed)?\b|\bbroke|regression"),
    ("performance", r"perf|faster|slow|speed"),
    ("refactor", r"refactor|restructur|clean ?up"),
    ("dependencies", r"dependenc|\bdeps\b|upgrade"),
    ("docs", r"\bdocs?\b|documentation"),
    ("feature", r"\bfeatures?\b"),
]
_RECENT = re.compile(r"\b(latest|recent(ly)?|newest|last (few |couple of )?(changes|commits|week|month)|lately|just changed)\b", re.I)
_TAG = re.compile(r"\bv?\d+\.\d+(\.\d+)?\b")


def _fold(text: str) -> str:
    """Lowercase without accents: 'Lucía' matches 'lucia'."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(ch))


def understand(repo_path: str, question: str) -> dict:
    """Filters a question implies, as insights.search understands them."""
    data = insights._load(repo_path)
    q = _fold(question)
    words = set(re.findall(r"[\w./-]+", q))
    found: dict = {}

    authors = {c["author"] for c in data["commits"]}
    for name in sorted(authors, key=len, reverse=True):  # full names first, then unique first names
        first = _fold(name).split()[0]
        if _fold(name) in q or (first in words and sum(_fold(a).split()[0] == first for a in authors) == 1):
            found["author"] = name
            break

    paths = {f for c in data["commits"] for f, _, _ in c["files"]}
    for w in sorted(words, key=len, reverse=True):
        w = w.strip("./")
        if ("/" in w or "." in w) and len(w) > 3 and not _TAG.fullmatch(w):
            if any(w in _fold(p) for p in paths):
                found["path"] = w
                break
        elif len(w) > 3 and any(_fold(PurePosixPath(p).stem) == w for p in paths):
            found["path"] = w  # a bare module name like "storage" or "auth"
            found["weak"] = True
            break

    tags = {r["name"] for r in insights.releases(repo_path)}
    for m in _TAG.finditer(q):
        for cand in (m.group(0), "v" + m.group(0), "v" + m.group(0) + ".0"):
            if cand in tags:
                found["release"] = cand
                break

    for cat, rx in _CATEGORY_WORDS:
        if re.search(rx, q):
            found["type"] = cat
            found["weak"] = True
            break
    if _RECENT.search(q):
        found["recent"] = True
    return found


def _filtered(repo_path: str, found: dict) -> list[str]:
    """Hashes matching the filters, newest first. If all together match nothing, each alone (most precise first)."""
    keys = [k for k in ("release", "author", "path", "type") if k in found]
    for group in [keys, *([k] for k in keys)] if len(keys) > 1 else [keys] if keys else []:
        query = " ".join(f'{k}:"{found[k]}"' for k in group)
        try:
            results = insights.search(repo_path, query, limit=FILTERED_MAX * 3)["results"]
        except Exception:  # a release that isn't a tag, etc.
            results = []
        if results:
            return [r["hash"] for r in _spread(results)]
    if found.get("recent"):
        return [c["hash"] for c in insights._load(repo_path)["commits"][:FILTERED_MAX]]
    return []


def _spread(results: list[dict]) -> list[dict]:
    """Up to FILTERED_MAX results, skipping repeats of the same subject (e.g. five 'Update screenshots')."""
    out, seen = [], set()
    for r in results:
        key = re.sub(r"\W+", " ", r["subject"].lower()).strip()
        if key not in seen:
            seen.add(key)
            out.append(r)
        if len(out) >= FILTERED_MAX:
            break
    return out


def _commit(repo_path: str, hash_: str) -> list[Commit]:
    return get_commits(repo_path, 1, rev=hash_)


def gather(repo_path: str, question: str, turns: Sequence[chat_engine.Turn] = (),
           previous: Sequence[Commit] = (), pinned: Sequence[str] = ()) -> list[Commit]:
    """Best-first candidate commits for a question (the prompt builder keeps as many as fit)."""
    follow_up = chat_engine.is_follow_up(question, turns)
    query = chat_engine.retrieval_query(question, turns)
    focused = [c for h in pinned for c in _commit(repo_path, h)]  # focused or tagged by the user
    # The chat stores only summaries of the commits an answer used; reload them in full.
    previous = [c for p in previous for c in _commit(repo_path, p["hash"])] if follow_up else []
    found = understand(repo_path, question) or (understand(repo_path, query) if follow_up else {})
    filtered = [c for h in _filtered(repo_path, found) for c in _commit(repo_path, h)]
    hits = vector_store.search(repo_path, query, top_k=SEMANTIC_TOP_K)
    if found.get("author"):  # "what did Priya do?": other people's commits are noise
        hits = [c for c in hits if c["author"] == found["author"]]
    # Names, releases, full paths and "latest" are reliable, so their matches lead. A bare word ("storage") or a
    # category keyword is a guess: the best meaning-based hits stay ahead of it.
    lead = 3 if found.get("weak") and not {"author", "release", "recent"} & found.keys() else 0
    candidates = chat_engine.candidate_commits([*focused, *hits[:lead], *filtered, *hits[lead:]], previous, follow_up)
    # Dig for *why*: the commits a revert undid, and other commits about the same issue.
    related = [c for h in insights.related(repo_path, [x["hash"] for x in candidates[:3]]) for c in _commit(repo_path, h)]
    return chat_engine.candidate_commits([*candidates[:3], *related, *candidates[3:]], [], False)
