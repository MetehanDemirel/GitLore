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

## Model

- **Default:** `Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF` → `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf` (1.12 GB, Apache-2.0). Code-aware, fast on CPU.
- **Optional "better answers" preset:** `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF` → `q4_k_m` (2.1 GB), slower.
- Model repo/filename live in one config dict in `model_manager.py` (and a sidebar dropdown), so swapping models is a one-line change.
- Avoid "thinking" models (e.g. Qwen3) for now: their `<think>` output complicates streaming for little gain at this size.
- Note: models must be supported by the llama.cpp bundled in 0.3.19 (March 2026).

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
6. **UI** — sidebar (repo path, commit count, model preset, Index button, status), chat, citations expander.
7. **Polish** — auto-shutdown watchdog, error messages, README with screenshot, license (MIT?).

## Claude Code skills to use while building (all already installed — nothing to download)

| When | Skill |
|---|---|
| Before phase 2 | `engineering:testing-strategy` — plan the pytest suite |
| While coding | `run` — launch Streamlit and verify in the browser pane |
| After each phase | `/code-review`, `/simplify` |
| Before publishing | `security-review` (user-supplied paths → subprocess `git`), `engineering:documentation` for README |

Not needed: `claude-api` (the app deliberately uses no Anthropic/OpenAI API).

## Open questions (decide later)

- License (MIT suggested — note Qwen2.5-Coder models are Apache-2.0).
- Also index file-level `git blame` for "who wrote this line" questions? (v2)
- Package as a `pipx`/`uv tool` installable CLI (`gitlore /path/to/repo`)? (v2)
