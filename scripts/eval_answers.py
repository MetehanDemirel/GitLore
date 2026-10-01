"""Answer-quality eval on the demo project with the real model.

    python scripts/eval_answers.py            # all cases
    python scripts/eval_answers.py jwt csv    # only cases whose name contains one of the words
    python scripts/eval_answers.py --hard     # plus 8 harder questions
    python scripts/eval_answers.py --hard --server http://localhost:11434 --model qwen3:8b   # a local server's model

Each case checks: the right commits reached the prompt (retrieval), the answer cites them (grounding),
no made-up hashes (hallucination), expected words appear, and no repeated sentences.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import chat_engine, config, demo, insights, model_manager, retrieval, vector_store  # noqa: E402
from src.git_parser import get_commits  # noqa: E402

# name, question, follow-up turns before it, commits that must be cited (any one of each group), words (any)
CASES = [
    ("jwt-why", "Why did we switch login to JWT?", [], [["04ad8dd"]], ["instance", "balancer", "scale"]),
    ("csv-revert", "Why was the CSV export reverted?", [], [["9758330", "11fef00"]], ["windows", "excel", "encoding", "newline", "broke"]),
    ("csv-back", "How did the CSV export come back?", [], [["74a2d62"]], ["windows"]),
    ("sqli", "Was there ever a SQL injection problem? How was it fixed?", [], [["e65b4c1"]], ["search", "parameter", "placeholder", "query"]),
    ("security-list", "List the security fixes.", [], [["e65b4c1", "457216d", "bd8949f", "a18f40d"]], ["security", "token", "injection", "rate"]),
    ("latest", "What are the latest changes?", [], [["3e6f26f", "bdebda7", "415f468", "eafadef"]], ["dependencies", "keyboard", "imports"]),
    ("who-most", "Who has made the most commits?", [], [], ["ada park"]),
    ("person", "What has Priya Nair worked on?", [], [["bd8949f", "457216d", "05938c8", "69277a4", "eafadef"]], ["security", "refactor", "cache", "rate"]),
    ("file", "How did taskflow/core/auth.py evolve?", [], [["04ad8dd", "831c7cc", "42a66f5", "bd8949f"]], ["jwt", "token", "password"]),
    ("release", "What changed in v1.1.1?", [], [["e65b4c1"]], ["security", "injection"]),
    ("dashboard", "Why was the web dashboard removed and brought back?", [], [["f860c76", "3fe74a4"]], ["paginat", "slow"]),
    ("sqlite", "Why did storage move from JSON to SQLite?", [], [["62916c8"]], ["json"]),
    ("follow-up", "Who did that?", [("Why was the CSV export reverted?", None)], [["9758330", "11fef00"]], ["sara"]),
    ("follow-up-2", "And when was it added back?", [("Why was the CSV export reverted?", None)], [["74a2d62"]], ["2026", "lucía", "lucia", "again", "added back"]),
    ("unknown", "Why did we add Kubernetes support?", [], [], ["no ", "not ", "doesn't", "don't", "isn't"]),
]

# Harder: two-part questions, exact facts buried in commit bodies, ranges, and a second trap (--hard).
HARD = [
    ("h-owner", "Who owns the auth code now, and why did ownership change?", [], [["5abf3be"]], ["another team", "moving"]),
    ("h-password", "Why was password hashing changed, and what did it replace?", [], [["42a66f5"]], ["sha-256", "sha256"]),
    ("h-cache", "Why does the API keep the task list in memory, and how much faster did it get?", [], [["69277a4"]], ["5x", "five times", "5 times"]),
    ("h-packages", "Why was the code split into packages, and what rule do the packages follow?", [], [["05938c8"]], ["one-way", "never each other", "not each other"]),
    ("h-ratelimit", "What attack led to rate-limiting logins, and what exactly is the limit?", [], [["457216d"]], ["15 minutes", "15-minute"]),
    ("h-range", "What were the main changes between v1.3.0 and v2.0.0?", [], [["3fe74a4", "99f0e6d", "457216d", "f860c76", "521bd67"]], ["dashboard", "paginat", "rate"]),
    ("h-chain", "The web dashboard was added, removed and added again. Explain each step and why.", [], [["521bd67", "f860c76"], ["3fe74a4"]], ["paginat"]),
    ("h-trap", "Why did we migrate from SQLite to PostgreSQL?", [], [], ["no ", "not ", "doesn't", "don't", "isn't", "never"]),
]

_CITE = re.compile(r"\[([0-9a-f]{7,40})\]")


def repeated_sentences(text: str) -> int:
    sents = [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 25]
    return len(sents) - len(set(sents))


def run_case(llm, path: str, known: set[str], case) -> dict:
    name, question, turns_spec, must_cite, words = case
    turns, previous = [], []
    for prev_q, _ in turns_spec:  # answer the earlier question for real, like the app does
        cands = retrieval.gather(path, prev_q)
        msgs, used = chat_engine.build_messages(llm, prev_q, cands)
        prev_a = "".join(chat_engine.stream_answer(llm, msgs))
        turns.append((prev_q, prev_a))
        previous = [{"hash": c["hash"]} for c in used]
    start = time.monotonic()
    cands = retrieval.gather(path, question, turns, previous)
    msgs, used = chat_engine.build_messages(llm, question, cands, turns)
    answer = "".join(chat_engine.stream_answer(llm, msgs))
    seconds = time.monotonic() - start
    in_prompt = {c["short_hash"] for c in used}
    cited = {h[:7] for h in _CITE.findall(answer)}
    fake = {h for h in cited if not any(k.startswith(h) for k in known)}
    retrieved = all(any(h in in_prompt for h in group) for group in must_cite)
    grounded = all(any(h in cited for h in group) for group in must_cite)
    worded = not words or any(w in answer.lower() for w in words)
    reps = repeated_sentences(answer)
    ok = retrieved and grounded and worded and not fake and not reps
    return {"name": name, "ok": ok, "retrieved": retrieved, "grounded": grounded, "worded": worded,
            "fake": sorted(fake), "repeats": reps, "seconds": round(seconds, 1),
            "prompt_tokens": sum(len(llm.tokenize(m["content"].encode(), add_bos=False)) for m in msgs),
            "answer": answer}


def main() -> None:
    path = str(demo.ensure_demo())
    config.CHROMA_DIR = config.DATA_DIR / "eval-chroma"  # never touches the app's index
    if vector_store.count(path) == 0:
        vector_store.index_commits(path, get_commits(path, 500))
    known = set(insights._load(path)["by_hash"])
    args = sys.argv[1:]
    opt = lambda name: args[args.index(name) + 1] if name in args else None  # noqa: E731
    if opt("--server"):  # e.g. --server http://localhost:11434 --model qwen3:8b
        from src import local_server
        llm = local_server.LocalServerLlm(opt("--server"), opt("--model"))
    else:
        llm = model_manager.load_llm(config.MODEL_PRESETS[config.DEFAULT_PRESET])
    cases = CASES + HARD if "--hard" in args else HARD if "--only-hard" in args else CASES
    words = [a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or args[i - 1] not in ("--server", "--model"))]
    picked = [c for c in cases if not words or any(w in c[0] for w in words)]
    results = [run_case(llm, path, known, c) for c in picked]
    for r in results:
        flags = [k for k in ("retrieved", "grounded", "worded") if not r[k]]
        flags += [f"fake {r['fake']}"] if r["fake"] else []
        flags += [f"{r['repeats']} repeats"] if r["repeats"] else []
        print(f"{'PASS' if r['ok'] else 'FAIL'} {r['name']:<14} {r['seconds']:>5}s {r['prompt_tokens']:>5} tok  {', '.join(flags)}")
        if "-v" in args or not r["ok"]:
            print("     " + r["answer"].replace("\n", "\n     ")[:900])
    print(f"\n{sum(r['ok'] for r in results)}/{len(results)} passed, "
          f"{sum(r['seconds'] for r in results) / len(results):.1f}s average")


if __name__ == "__main__":
    main()
