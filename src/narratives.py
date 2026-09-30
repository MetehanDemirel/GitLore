"""AI-written, cited narratives about a repository: its history, a timeline of key events,
"what changed while I was away?" and an onboarding brief.

The structure (eras, events, statistics) is computed from Git without the model, so it is instant
and always correct. The model only writes the prose, in small prompts (one per era or per batch of
events), and every claim cites commits. Results are cached by the caller (see server.py).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta

from src import chat_engine, config, insights

Progress = Callable[[int, int, str], None]
CODE_SUFFIXES = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".c", ".cc", ".cpp", ".h",
                 ".cs", ".rb", ".php", ".swift", ".html", ".vue", ".svelte", ".scala", ".dart", ".lua")

_ERA_PROMPT = (
    "You write short, factual history for a software project. Use ONLY the commits listed. "
    "Explain what changed in this period and, where the commit messages say so, WHY. "
    "Cite commits with their short hash in square brackets, e.g. [a1b2c3d]. 2 to 4 sentences. No lists."
)
_INTRO_PROMPT = (
    "You write the opening paragraph of a software project's history, from summaries of its periods. "
    "3 sentences: what the project is, how it evolved, and where it is now. Keep the citations from the "
    "summaries exactly as written; never invent a commit hash."
)
_EVENTS_PROMPT = (
    "For each numbered change, write ONE short sentence explaining why it happened, based only on its "
    "message. Answer as a numbered list with the same numbers. If the message gives no reason, say what it did."
)
_AWAY_PROMPT = (
    "Someone was away from this project and wants to catch up. Using ONLY the commits and facts listed, "
    "write 3 to 6 short bullet points about the most important changes, most important first "
    "(security and breaking changes before small fixes). Cite commits like [a1b2c3d]."
)
_ONBOARD_PROMPT = (
    "Write a short welcome brief for a developer joining this project, using ONLY the facts listed: "
    "what the project does, how it evolved, who works on which areas, and where to start reading. "
    "About 120 words, plain paragraphs, cite commits like [a1b2c3d]."
)


# ============================================================================ model helper
def _generate(llm, system: str, user: str, language: str, max_tokens: int = 260) -> str:
    if getattr(llm, "metadata", {}).get("general.architecture") == "qwen3":
        system += " /no_think"
    if language != "en" and language in chat_engine.ANSWER_LANGUAGES:
        name = chat_engine.ANSWER_LANGUAGES[language]
        system += f" Always write in {name}."
        user += f"\n\n(Write in {name}.)"
    pieces = chat_engine._strip_think(
        chunk["choices"][0]["delta"].get("content") or ""
        for chunk in llm.create_chat_completion(messages=[{"role": "system", "content": system},
                                                          {"role": "user", "content": user}],
                                                stream=True, max_tokens=max_tokens, temperature=0.2,
                                                repeat_penalty=1.1))
    return "".join(pieces).strip()


_CITE_RE = re.compile(r"\[([0-9a-f]{7,40})\]")


def clean_citations(repo_path: str, text: str) -> str:
    """Drop citations of commits that don't exist (small models sometimes copy the prompt's example hash)."""
    known = insights._load(repo_path)["by_hash"]

    def keep(m: re.Match) -> str:
        return m.group(0) if any(k.startswith(m.group(1)) for k in known) else ""

    return re.sub(r"\s+([.,;:])", r"\1", _CITE_RE.sub(keep, text)).strip()


def _line(c: dict, with_body: bool = True, body_chars: int = 220) -> str:
    body = (c.get("body") or "").replace("\n", " ").strip()
    text = f"[{c['short_hash']}] {c['date'][:10]} {c['author']} ({c['category']}): {c['subject']}"
    if with_body and body:
        text += f" — {body[:body_chars]}"
    return text


def _notable(commits: list[dict], limit: int = 8) -> list[dict]:
    rank = {"security": 0, "performance": 2, "feature": 3, "revert": 1, "bugfix": 4, "refactor": 5}
    scored = [c for c in commits if c["category"] in rank or c["large"]]
    # Commits that explain themselves (a message body) matter more than one-line housekeeping.
    scored.sort(key=lambda c: (0 if c["large"] else 1, 0 if len(c.get("body") or "") > 30 else 1,
                               rank.get(c["category"], 6), c["date"]))
    return sorted(scored[:limit], key=lambda c: c["date"])


# ============================================================================ eras & history
def eras(repo_path: str) -> list[dict]:
    """Periods of the project: one per release (plus unreleased work), or equal time slices without tags."""
    commits = list(reversed(insights.all_commits(repo_path)))  # oldest first
    if not commits:
        return []
    rels = list(reversed(insights.releases(repo_path)))       # oldest first
    by_hash = {c["hash"]: c for c in commits}
    out, seen = [], set()
    if rels:
        from src.git_parser import open_repo
        repo = open_repo(repo_path)
        for r in rels:
            rng = f"{r['previous']}..{r['name']}" if r["previous"] else r["name"]
            hashes = [h for h in repo.git.rev_list(rng).split() if h in by_hash and h not in seen]
            seen.update(hashes)
            if hashes:
                out.append({"key": r["name"], "title": r["name"], "release": r["name"], "tag_message": r["message"],
                            "commits": sorted((by_hash[h] for h in hashes), key=lambda c: c["date"])})
        rest = [c for c in commits if c["hash"] not in seen]
        if rest:
            out.append({"key": "unreleased", "title": "Unreleased", "release": None, "tag_message": "", "commits": rest})
    else:
        size = max(1, len(commits) // 6 + 1)
        for i in range(0, len(commits), size):
            chunk = commits[i:i + size]
            out.append({"key": f"slice-{i // size}", "title": f"{chunk[0]['date'][:7]} – {chunk[-1]['date'][:7]}",
                        "release": None, "tag_message": "", "commits": chunk})
    for era in out:
        cs = era["commits"]
        era.update(start=cs[0]["date"], end=cs[-1]["date"], count=len(cs),
                   categories=dict(Counter(c["category"] for c in cs).most_common()),
                   contributors=[a for a, _ in Counter(c["author"] for c in cs).most_common(4)],
                   notable=[insights._brief(c) for c in _notable(cs)])
    return out


def repository_history(repo_path: str, llm, language: str, progress: Progress) -> dict:
    periods = eras(repo_path)
    total = len(periods) + 1
    written = []
    for i, era in enumerate(periods):
        progress(i, total, era["title"])
        notable = _notable(era["commits"])
        facts = [f"Period: {era['title']} ({era['start'][:10]} to {era['end'][:10]}), {era['count']} commits.",
                 f"Contributors: {', '.join(era['contributors'])}.",
                 f"Kinds of change: {', '.join(f'{k} {v}' for k, v in list(era['categories'].items())[:6])}."]
        if era["tag_message"]:
            facts.append(f"Release notes: {era['tag_message'][:400]}")
        facts.append("Notable commits:\n" + "\n".join(_line(c) for c in notable))
        summary = clean_citations(repo_path, _generate(llm, _ERA_PROMPT, "\n".join(facts), language, 240)) if llm else ""
        written.append({k: v for k, v in era.items() if k != "commits"} | {"summary": summary})
    progress(len(periods), total, "intro")
    intro = ""
    if llm and written:
        joined = "\n".join(f"{e['title']} ({e['start'][:10]}): {e['summary']}" for e in written)[:3500]
        intro = clean_citations(repo_path, _generate(llm, _INTRO_PROMPT, joined, language, 200))
    progress(total, total, "done")
    return {"intro": intro, "eras": list(reversed(written))}


# ============================================================================ timeline
def events(repo_path: str) -> list[dict]:
    """Key moments, computed from Git: releases, security fixes, big changes, reverts, performance work,
    notable features, and people joining or moving on."""
    commits = list(reversed(insights.all_commits(repo_path)))
    if not commits:
        return []
    out = []
    for r in insights.releases(repo_path):
        out.append({"date": r["date"], "kind": "release", "title": r["name"], "detail": r["message"].split("\n")[0],
                    "hashes": [r["hash"]], "author": r["tagger"]})
    for c in commits:
        explained = len(c.get("body") or "") > 30
        kind = ("large" if c["large"] else c["category"] if c["category"] in ("security", "revert")
                else "performance" if c["category"] == "performance" and explained else None)
        if kind:
            out.append({"date": c["date"], "kind": kind, "title": c["subject"], "detail": "",
                        "hashes": [c["hash"]], "author": c["author"]})
    features = [c for c in commits if c["category"] == "feature" and c["parents"] == 1 and len(c.get("body") or "") > 40]
    for c in features:
        out.append({"date": c["date"], "kind": "feature", "title": c["subject"], "detail": "",
                    "hashes": [c["hash"]], "author": c["author"]})
    first, last = {}, {}
    for c in commits:
        first.setdefault(c["author"], c)
        last[c["author"]] = c
    end = datetime.fromisoformat(commits[-1]["date"])
    start = datetime.fromisoformat(commits[0]["date"])
    for author, c in first.items():
        if datetime.fromisoformat(c["date"]) - start > timedelta(days=14):
            out.append({"date": c["date"], "kind": "joined", "title": f"{author} joined", "detail": c["subject"],
                        "hashes": [c["hash"]], "author": author})
    for author, c in last.items():
        if end - datetime.fromisoformat(c["date"]) > timedelta(days=120):
            out.append({"date": c["date"], "kind": "left", "title": f"{author}'s last commit", "detail": c["subject"],
                        "hashes": [c["hash"]], "author": author})
    out.sort(key=lambda e: e["date"], reverse=True)
    for e in out:
        e["short_hashes"] = [h[:7] for h in e["hashes"]]
    return out


def timeline(repo_path: str, llm, language: str, progress: Progress) -> dict:
    evs = events(repo_path)
    by_hash = insights._load(repo_path)["by_hash"]
    explain = [e for e in evs if e["kind"] not in ("joined", "left", "release")]
    batches = [explain[i:i + 6] for i in range(0, len(explain), 6)]
    for n, batch in enumerate(batches):
        progress(n, len(batches), "")
        if not llm:
            break
        lines = [f"{i + 1}. {_line(by_hash[e['hashes'][0]], body_chars=260)}" for i, e in enumerate(batch)]
        text = _generate(llm, _EVENTS_PROMPT, "\n".join(lines), language, 60 * len(batch))
        for i, e in enumerate(batch):
            m = re.search(rf"(?m)^\s*{i + 1}[.)]\s*(.+)$", text)
            if m:
                e["why"] = clean_citations(repo_path, m.group(1).strip())
    progress(len(batches), len(batches), "done")
    return {"events": evs}


# ============================================================================ catching up
def away_facts(repo_path: str, since_iso: str) -> dict:
    """Non-AI summary of everything since a date (shown instantly, before the AI briefing)."""
    cs = insights.commits_since(repo_path, since_iso)
    rels = [r for r in insights.releases(repo_path) if r["date"] >= since_iso]
    return {"since": since_iso, "count": len(cs),
            "categories": dict(Counter(c["category"] for c in cs).most_common()),
            "contributors": [{"name": a, "commits": n} for a, n in Counter(c["author"] for c in cs).most_common()],
            "releases": [{"name": r["name"], "date": r["date"], "message": r["message"].split("\n")[0]} for r in rels],
            "notable": [insights._brief(c) for c in _notable(cs, 10)],
            "large": [insights._brief(c) for c in cs if c["large"]]}


def away(repo_path: str, since_iso: str, llm, language: str, progress: Progress) -> dict:
    facts = away_facts(repo_path, since_iso)
    progress(0, 1, "")
    briefing = ""
    if llm and facts["count"]:
        by_hash = insights._load(repo_path)["by_hash"]
        lines = [f"Since {since_iso[:10]}: {facts['count']} commits by "
                 f"{', '.join(c['name'] for c in facts['contributors'][:6])}.",
                 f"Kinds of change: {', '.join(f'{k} {v}' for k, v in list(facts['categories'].items())[:6])}."]
        if facts["releases"]:
            lines.append("Releases: " + "; ".join(f"{r['name']} ({r['message']})" for r in facts["releases"]))
        lines.append("Most important commits:\n" + "\n".join(_line(by_hash[c["hash"]]) for c in facts["notable"]))
        briefing = clean_citations(repo_path, _generate(llm, _AWAY_PROMPT, "\n".join(lines), language, 320))
    progress(1, 1, "done")
    return {**facts, "briefing": briefing}


def onboarding_facts(repo_path: str) -> dict:
    from src.git_parser import open_repo
    existing = set(open_repo(repo_path).git.ls_files("-z").split("\0"))  # files that still exist today
    ov = insights.overview(repo_path)
    people = insights.contributors(repo_path)
    rels = insights.releases(repo_path)
    return {"overview": ov, "contributors": [{"name": p["name"], "commits": p["commits"], "areas": p["areas"],
                                              "last": p["last"]} for p in people[:8]],
            "releases": [{"name": r["name"], "date": r["date"], "message": r["message"].split("\n")[0]} for r in rels[:6]],
            "start_here": [h["path"] for h in insights.hot_files(repo_path, 80) if h["path"] in existing
                           and h["path"].endswith(CODE_SUFFIXES) and not h["path"].startswith(("docs/", "tests/"))][:5]}


def onboarding(repo_path: str, llm, language: str, progress: Progress) -> dict:
    facts = onboarding_facts(repo_path)
    progress(0, 1, "")
    brief = ""
    if llm:
        by_hash = insights._load(repo_path)["by_hash"]
        ov = facts["overview"]
        key = [e for e in events(repo_path) if e["kind"] not in ("joined", "left")][:10]
        lines = [f"{ov['commits']} commits from {ov['first'][:10]} to {ov['last'][:10]} by {ov['contributors']} people.",
                 "People and their areas: " + "; ".join(f"{p['name']} ({', '.join(p['areas'][:2])})"
                                                        for p in facts["contributors"][:6]),
                 "Releases: " + "; ".join(f"{r['name']} {r['date'][:10]}: {r['message']}" for r in facts["releases"]),
                 "Most-changed code: " + ", ".join(facts["start_here"]),
                 "Key changes:\n" + "\n".join(_line(by_hash[e["hashes"][0]], body_chars=150)
                                              for e in key if e["hashes"][0] in by_hash)]
        brief = clean_citations(repo_path, _generate(llm, _ONBOARD_PROMPT, "\n".join(lines)[:5000], language, 320))
    progress(1, 1, "done")
    return {**facts, "brief": brief}


def default_since(last_visit: str | None) -> str:
    """'Since my last visit', or 30 days before the latest commit when there is no visit yet."""
    if last_visit:
        return last_visit
    return (datetime.now().astimezone() - timedelta(days=30)).isoformat(timespec="seconds")


__all__ = ["away", "away_facts", "default_since", "eras", "events", "onboarding", "onboarding_facts",
           "repository_history", "timeline", "config"]
