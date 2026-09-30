# GitLore — Project Plan

**GitLore** is a local "Git archaeologist": point it at a repository on disk and ask plain-English
questions about how and why the code changed. It reads commit history, indexes it for semantic search,
and answers with a small local LLM — citing commit hashes and authors.

## Goals & constraints

| Goal | Decision |
|---|---|
| Free, private, offline after first run | No paid APIs. Everything runs on the user's machine. |
| Seamless setup for anyone on GitHub | `pip`/`uv` install only — **no compiler, no CUDA, no Ollama, no Docker**. |
| Works on ordinary hardware | **CPU-only** by design. Default model is ~1.1 GB and runs in ~2–3 GB RAM. |
| Nothing lingers after use | LLM runs *in-process*; the app shuts itself down when the browser tab is closed. |
| Cross-platform | Windows, Linux, Apple Silicon Mac (Intel Mac works but builds llama.cpp from source). |

**Non-goals (v1):** GPU acceleration, remote repos/URLs, multi-user hosting, code-file (non-history) search.

## Tech stack (verified installable 2026-09-30, Python 3.12, Windows, no compiler)

| Concern | Package | Notes |
|---|---|---|
| UI | `streamlit` | Chat UI via `st.chat_message` / `st.chat_input` / `st.write_stream`. |
| Git parsing | `GitPython` | Needs the `git` CLI on PATH. |
| LLM runtime | `llama-cpp-python==0.3.19` | Pinned: newest version with prebuilt CPU wheels (installed from the project's wheel index). PyPI only has source for newer versions. |
| Model download | `huggingface-hub` (<2) | `hf_hub_download` on first run. Capped <2 for `tokenizers` compatibility. |
| Vector DB + embeddings | `chromadb` | Uses Chroma's **built-in** `all-MiniLM-L6-v2` (ONNX, ~80 MB). **No `sentence-transformers` / PyTorch** (saves ~2 GB). |

Why not GPU? `llama-cpp-python` has no prebuilt Windows CUDA wheels; GPU support would mean
requiring Visual Studio + CUDA Toolkit, or an external Ollama install. Both break "seamless setup".
The code still passes `n_gpu_layers=-1`, so anyone who *manually* installs a GPU build gets it for free —
but that's undocumented/unsupported territory.

## Model choice

**Default: Qwen3-1.7B** (`unsloth/Qwen3-1.7B-GGUF` → `Qwen3-1.7B-Q4_K_M.gguf`, 1.1 GB, Apache-2.0, no login).
Sent with `/no_think` so it skips its hidden reasoning step; any `<think>` block is stripped from the stream.
Other models can still be used via *Custom GGUF* in the side panel. Presets live in `src/config.py`.

**How it was chosen (2026-09-30).** Priorities: responsiveness first, reliability second. Each model ran
GitLore's real pipeline (same retrieval, same 1,800-token prompt budget) on 300 commits of `psf/requests`,
i5-11400H CPU, Q4 quantization. Five questions with known answers: why / who / when+who / "what did
<hash> change" / and a trap question the history can't answer. 2 points each: cites the right commit +
states the right fact; for the trap, says it isn't in the commits. Retrieval ranked the right commit #1 for
every question, so differences are the model's.

| Model | Size | First word | Tokens/s | Score |
|---|---|---|---|---|
| **Qwen3-1.7B** | 1.1 GB | 10.2 s | 24 | **9/10** |
| Qwen3-4B-Instruct-2507 | 2.4 GB | 25.8 s | 10 | 9/10 |
| LFM2-2.6B | 1.6 GB | 16.0 s | 20 | 8/10 |
| Qwen2.5-Coder-3B (old "better" preset) | 2.1 GB | 17.8 s | 14 | 7/10 |
| LFM2.5-1.2B | 0.7 GB | 6.7 s | 38 | 5/10 |
| Llama-3.2-1B | 0.8 GB | 6.4 s | 32 | 5/10 |
| Qwen2.5-Coder-1.5B (old default) | 1.1 GB | 9.5 s | 26 | 4/10 |
| Qwen3.5-0.8B / 2B | — | — | — | won't load (architecture newer than llama.cpp in 0.3.19) |
| Gemma 3 1B | — | — | — | skipped: gated download needs a Hugging Face login |

Only the Qwen3 models answered the trap question honestly; every other model invented a reason. The two
fastest models (LFM2.5, Llama 3.2) are ~35% quicker to the first word but half as reliable. Qwen3-4B matched
Qwen3-1.7B's score at 2.5× the wait, so there is no second preset. Revisit when llama-cpp-python ships wheels
new enough for Qwen3.5 (it may be both faster and better). Small sample: 5 questions, one repo.

## Architecture & data flow

```
repo path ─► git_parser ─► commit dicts ─► vector_store (Chroma, persisted per repo)
                                                  │
question ─────────────────────────► search(top_k) ┘
                                                  ▼
                                chat_engine: build prompt (token-budgeted) ─► llama.cpp ─► stream ─► Streamlit
```

1. **Ingest** — `get_commits(repo_path, max_count)` → list of `{hash, short_hash, author, date, message, files_changed, diff_summary}`.
2. **Index** — one Chroma document per commit (`message + file list + truncated diff`), metadata = hash/author/date.
   Collection per repo (name = hash of the absolute repo path). **Incremental:** skip hashes already indexed.
3. **Retrieve** — embed question, fetch top-k (default 5).
4. **Generate** — system prompt + retrieved commits packed into a **token budget** (see below) + question → stream tokens.
5. **Render** — `st.write_stream`; show the cited commits in an expander under each answer.

## Directory structure

```text
GitLore/
├── app.py               # Streamlit UI + auto-shutdown watchdog
├── requirements.txt
├── start.bat / start.sh # one-click: create venv (uv), install, run
├── README.md            # user-facing (from SETUP.md)
├── .gitignore           # .venv/, data/, __pycache__/
├── src/
│   ├── config.py        # paths, model presets, limits (single source of truth)
│   ├── model_manager.py # download + load Llama (cached with st.cache_resource)
│   ├── git_parser.py    # GitPython → commit dicts
│   ├── vector_store.py  # Chroma PersistentClient at data/chroma/
│   └── chat_engine.py   # prompt building, token budgeting, streaming
├── tests/               # pytest: parser on a temp repo, prompt budgeting, store round-trip
└── data/                # git-ignored: models/, chroma/
```

## Key design details (things the original spec missed)

- **Context budget.** `n_ctx=4096`. Reserve ~512 for the answer and ~300 for system prompt + question; pack
  commits until the rest is used. Truncate each diff to N lines/chars. Count tokens with `llm.tokenize()`.
- **Big repos.** `max_count` slider (default 200, max ~2000). Skip merge commits' diffs and binary files.
  Show a progress bar during indexing. Indexing is embeddings-only (fast); the LLM is not used for ingestion.
- **Threads.** `n_threads = max(1, os.cpu_count() // 2)` (physical-core approximation) instead of hard-coded 4.
- **Caching.** `@st.cache_resource` for the `Llama` instance and Chroma client — loaded once per process, not per rerun.
- **Validation.** Friendly errors for: path doesn't exist, not a git repo, empty repo, `git` not installed, model download failure / no internet on first run.
- **Model storage.** Download to `data/models/` (`local_dir=`), so users can see and delete it; show size + progress on first run.
- **Auto-shutdown ("closes itself").** A daemon thread in `app.py` polls Streamlit's active-session count
  (`Runtime.instance()._session_mgr.num_active_sessions()`, internal API — wrap in try/except and disable if
  unavailable). If zero sessions for ~30 s after at least one connected, `os._exit(0)`. The LLM is in-process,
  so nothing is left running. Closing the terminal window also kills everything.
- **Prompt.** System: *"You are GitLore, an assistant analyzing a Git repository. Answer using ONLY the commits
  below. Cite the short commit hash and author for every claim. If the commits don't answer the question, say so."*
  Use `create_chat_completion(stream=True)` so the model's own chat template is applied.

## Implementation phases

1. **Scaffold** ✅ — `config.py`, `.gitignore`, `.streamlit/config.toml`, `start.bat`/`start.sh`, module stubs with final signatures, `tests/test_config.py`, `requirements-dev.txt`. Verified: `start.bat` fresh install + relaunch on Windows.
2. **Git parser** ✅ — `get_commits()` via one streamed `git log -p -U0 --diff-merges=first-parent`; diffs truncated
   while streaming; lock/generated files listed but diff skipped; friendly `RepoError`s. 15 tests on real temp repos.
   Benchmark (psf/requests): 2,000 commits in 0.8 s, 5 MB peak memory.
3. **Vector store** ✅ — `index_commits()` (incremental, batched, progress callback), `search()` (semantic + exact
   commit-hash matching), `count()`, `reset()`; telemetry disabled; cosine distance; 8 tests.
   Benchmark (psf/requests, i5-11400H): index ~28 commits/s (2,000 in ~70 s), re-check 0.1 s, search ~0.3 s.
4. **Model manager** ✅ — presets + custom Hugging Face GGUF, download with byte progress (resumable), delete,
   CPU load (`n_threads` = physical cores, `n_threads_batch` = all cores), friendly `ModelError`s.
5. **Chat engine** ✅ — prompt capped at `MAX_PROMPT_TOKENS` (1,800) measured with the model's tokenizer; diffs
   trimmed to 600 chars in the prompt; message-only fallback; short follow-ups reuse the previous turn's commits.
   Measured on i5-11400H: first word after ~12–15 s (was ~28 s with a full 3,500-token prompt), ~25 tokens/s after.
6. **UI** ✅ — side panel with *Model* (preset or custom GGUF, download with progress, remove) and *Repository*
   (path, commit count, index/update/rebuild with progress) sections; "Get started" checklist until ready; chat
   with status line, streamed answers, hash citations linked to GitHub/GitLab, *Sources* expander; example
   questions; follows system light/dark theme; remembers last repo/model in `data/settings.json`.
7. **Release v0.1.0** ✅ — MIT license, CHANGELOG, CI on Windows/macOS/Linux × Python 3.11–3.13 plus a
   real-launcher job per OS, release workflow. Found via CI: Linux needs a source build of llama-cpp-python
   (upstream Linux wheel is musl-only); macOS + 3.13 upstream wheel is corrupt (launcher uses 3.12).
   Released 2026-09-30. Remaining: README screenshot.

---

# v0.2 — GitLore Workspace (planned 2026-09-30)

Turn GitLore from a chat page into a small **VS Code-like workspace for Git history**: browse commits,
see colored diffs, select code and ask the AI about it, edit files and commit, with saved projects and
chats, four languages and a dark theme.

## Decisions

| # | Decision | Choice | Why |
|---|---|---|---|
| D1 | Frontend | **New web UI with Monaco** (VS Code's editor), served by a small Python API. Streamlit is removed. | Real diff view, right-click menus, themes and shortcuts come built in. All of `src/` is reused unchanged. Streamlit couldn't give a VS Code feel. |
| D2 | Frontend build | **No build step**: plain ES modules + Preact/htm (0.7 MB, vendored in the repo). | Keeps "clone → double-click start" working. Contributors and users never need Node.js. Revisit only if the UI outgrows it. |
| D3 | Shipping Monaco | **Downloaded once on first launch** (18.6 MB, pinned version, sha512 integrity check), like the model. Only `min/vs` (25.6 MB) is kept. | Too big to commit; offline after first run. |
| D4 | "Edit commits" | **Edit files in the working tree, then make a new commit.** Past commits are read-only. No amend, rebase or force. | Normal, safe Git. Rewriting history can destroy work. |
| D5 | Languages | **English, Turkish, French, German** for the whole UI, and the AI is told to answer in the chosen language. | Qwen3 is multilingual. Answer quality in TR/FR/DE will be benchmarked like the model choice was. |
| D6 | Theme | **Light / Dark / System** toggle. Monaco switches between its `vs` and `vs-dark` themes to match. | |
| D7 | Projects & chats | A **project** = one local repository + its settings + its chats. Stored in **SQLite** (`data/gitlore.db`, stdlib, no new dependency). A chat can be anchored to a commit, file or selection. | Survives restarts; easy to list, rename, delete, export. |
| D8 | Demo data | **"Try the Demo Project"** button generates a small Git repo on first use from a script: a toy app with a meaningful story (add login → switch to JWT → fix a bug → refactor → revert). | Users and our tests can try everything instantly. Generated rather than committed, so it's small and reproducible. |
| D9 | Web server | **Starlette + uvicorn** (already installed as Streamlit dependencies), with server-sent events for streaming answers. | Dropping Streamlit also removes ~180 MB (pyarrow, pandas, pydeck, altair): faster install. |
| D10 | UI testing | API with pytest (`TestClient`); UI flows (right-click, diff, theme, language) with **Playwright**, in CI only (dev dependency). | Streamlit's AppTest goes away with Streamlit; right-click and diffs need a real browser. |

## Screen layout

```
+-------------+------------------------------------------+----------------+
| PROJECTS  v | a1b2c3d  Switch login to JWT · Ada · 3d  | AI ASSISTANT   |
|  my-app     |------------------------------------------|                |
|  demo       |  auth/login.py          (side-by-side)   |  > Why did     |
|-------------|  - session.save(user)   + issue_jwt(u)   |    this change?|
| COMMITS   / |                                          |                |
|  a1b2c3d  * |  select text -> right-click:             |  Sessions did  |
|  9f8e7d6    |     "Ask GitLore about this"             |  not scale...  |
|  ...        |     "Explain this change"                |  [a1b2c3d] Ada |
|-------------|                                          |                |
| CHATS       |  [Edit file]  [Commit...]                |  [ Ask... ]    |
+-------------+------------------------------------------+----------------+
 status bar: model ready · 200 commits indexed · EN | Dark
```

## Phases

| Phase | Goal | Done when |
|---|---|---|
| **8. Foundation** ✅ | Starlette API over `src/`, static web shell (3-panel layout), theme toggle, i18n plumbing (EN strings), model download + indexing + chat with streaming ported. Streamlit removed. Launchers, CI and auto-shutdown updated (shutdown via page heartbeat). | Feature parity with v0.1 in the new UI; all CI green |
| **9. Projects, chats & demo** ✅ | SQLite store; open/switch/new project; chat list with history (rename, delete); demo-project generator. | Restart the app and everything is still there; demo works offline |
| **10. Commit explorer & diffs** ✅ | Commit list with search/filter; files changed per commit; Monaco diff (side-by-side and inline, colored). | Any commit's changes can be browsed like in VS Code |
| **11. Ask AI from the code** ✅ | Right-click on a selection → "Ask GitLore" / "Explain this change"; the question carries the selection, file and commit as context; the assistant panel sits beside the diff. | Selection questions are answered with correct citations |
| **12. Edit & commit** ✅ | Open a working-tree file in Monaco, edit, see the diff vs. HEAD, write a message, commit. Guards: shows `git status`, refuses to commit on detached HEAD or during merges/rebases. | A commit made in GitLore shows up in `git log` exactly like a CLI commit |
| **13. Languages & release v0.2** ✅ | TR/FR/DE translations; AI answer-language benchmark; accessibility pass (keyboard, screen reader, contrast); screenshots; docs. | v0.2.0 released with CI green on 3 OSes |

Shipped as **v0.2.0**, then **v0.2.1** (browser tests fixed and run in CI). Changes from the plan:
D8 became a **built-in demo project** that is open on first launch (not a "Try the Demo" button);
Monaco's own menus are translated too; small models answered Turkish questions in English until the
answer language was repeated right after the question.

The earlier "better answers" ideas (exact-name search, date and author questions) move to v0.3+ below.

## Risks

- **Scope:** this rebuilds the interface. Phase 8 must reach parity before new features, so `main` never has a half-working UI. Work happens on a `v0.2` branch until phase 8 is green.
- **Translation quality:** a 1.7B model's Turkish/French/German answers may be weaker than its English ones. D5 includes a benchmark; if one language is poor, the UI still translates and the answer shows a note.
- **Monaco download:** first launch needs internet for both model and Monaco (already true for the model).

## Skills to use

| When | Skill |
|---|---|
| Phase 8 layout and look | `frontend-design`, `web-design-guidelines` |
| UI tests (right-click, diffs) | `webapp-testing` (Playwright) |
| Each phase | `/code-review`, `/simplify`, `security-review` for phase 12 (writes to the user's repo) |
| Phase 13 | `design:accessibility-review`, `engineering:documentation` |

## Open questions (decide later)

- Also index file-level `git blame` for "who wrote this line" questions? (see phase 18)
- Package as a `pipx`/`uv tool` installable CLI (`gitlore /path/to/repo`)?

---

# v0.3 and beyond — roadmap (planned 2026-09-30)

GitLore should explain **why** a codebase became what it is, not just list what changed; help people
who are new or coming back catch up; and stay calm to look at. Everything below is local and offline
by default; the online mode is a separate, opt-in addition.

## Principles

- **Zen by default.** New views live behind the activity bar and open on demand. Every panel can be
  hidden; a Zen mode shows only the editor (or only the chat). Colors are used for meaning, not decoration.
- **Instant first, AI second.** Anything that can be computed from Git directly (categories, contributors,
  churn, heatmaps, releases) is computed without the model, so it is instant. The model is used for the
  parts only language can do (stories, "why", summaries) and its results are **cached** in SQLite with a
  Regenerate button, because on a CPU they take seconds to minutes.
- **Every AI claim links to its evidence.** Timeline events, summaries and profiles cite commits you can click.

## Phases

| Phase | What you get | Done when |
|---|---|---|
| **14. Calm workspace & details** (v0.3) | Hide/show each sidebar (buttons + shortcuts, remembered); **Zen mode** (editor only, or chat only); more color themes beyond light/dark (e.g. high contrast, solarized light/dark, sepia, a dimmed dark) built as token sets; **Explain buttons** without right-click: "Explain This Commit" in the commit header and a small "Explain" action per changed block in the diff; languages **Spanish, Italian, Chinese (Simplified)** added (UI, Monaco menus, answers, benchmarked like TR/FR/DE). | All panels hideable; 6+ themes pass contrast checks; 7 languages pass `test_i18n.py` |
| **15. A bigger TaskFlow demo** (v0.3) | Regenerated demo with enough history to exercise everything below: ~2 years, ~200 commits, 6–8 fictional contributors who join and leave, feature branches and merges, tags **v1.0 → v2.x** with release notes, a large refactor, a security fix, a performance fix, reverts, renames, commit messages referencing issues (#12) and pull requests. Still generated, deterministic (identical hashes everywhere) and small on disk. | Every view in phases 16–18 shows meaningful data on the demo |
| **16. Insights, without AI** (v0.3) | New **Insights** view: commit **categories** (feature, bug fix, refactor, performance, security, docs, tests, dependencies, **large change**) from message conventions, keywords and changed-file types, shown as small chips and usable as filters; **contributors** (involvement, areas they own, active periods); **hot files / churn**; a **commit heatmap** (calendar); activity over time. **Release explorer** (tags, what changed between releases); **branch view**; **compare** any two commits, branches or tags. | Opens instantly on a 2,000-commit repo; everything links to commits |
| **17. The story of a repository** (v0.4) | **Generate Repository History**: an AI-written, cited narrative of how the project evolved, in eras. An **AI timeline** of key events (big features, rewrites, security fixes, releases), where clicking an event opens its commits. **"What changed while I was away?"**: pick a date (or "since my last visit") and get a short briefing. **Onboarding brief** for newcomers: the project in a page (major changes, key contributors, where to start reading). **Dig for "why"**: answers follow issue/PR references, related commits touching the same code, and reverts, before answering. Cached per project; regenerated on demand. | Briefings on the demo are accurate, cite commits, and regenerate in minutes on a laptop CPU |
| **18. People and search** (v0.4) | **Minimal developer profiles** (what someone worked on, when, their areas; no rankings or scores); **"who knows this code?"** from line history (`git blame`); **advanced search** with filters (`author:`, `path:`, `type:`, `since:`/`until:`, `release:`) combined with meaning-based search, and saved searches. | Search answers "security fixes in auth/ last year by Leo" in one query |
| **19. Online mode** (v0.5, opt-in) | Paste a GitHub URL (for example `github.com/microsoft/vscode`) → GitLore clones it and adds it as a project. Periodic **live** updates (fetch) while open; **related discussions** (pull requests, issues and reviews linked to a commit); GitHub releases in the release explorer. Clearly marked as online; everything else keeps working offline. | A public repo can be added by URL and its commits link to their PRs |
| **20. Private repositories** (v0.5, needs a decision) | See the open question below. | — |

## Decisions still needed

- **GitHub sign-in for private repositories (phase 20).** Options: (a) **public repos only** at first, no
  login (simplest, no secrets stored); (b) paste a **fine-grained personal access token**, stored in the
  OS keychain, read-only scope; (c) **"Sign in with GitHub"** via the device flow (no password typed into
  GitLore, lists your repos to import). Recommended path: ship (a) with phase 19, then (c) with (b) as the
  fallback for GitHub Enterprise. Large repos (vscode has 100k+ commits) need a commit-count limit or a
  shallow first import either way.
- Which extra themes exactly (phase 14), and whether profiles show any numbers at all (phase 18).

## Risks

- **CPU time for AI narratives.** Summarizing hundreds of commits with a 1.7B model takes minutes. Plan:
  work in chunks (per era/release), cache every result, show progress, never block the UI.
- **Categorization accuracy.** Rules are fast but imperfect; categories show as "suggested" and the
  model only re-checks ambiguous commits.
- **Scope creep vs. calm UI.** Each phase adds at most one new activity-bar view; the rest goes into
  existing views or on-demand panels.
