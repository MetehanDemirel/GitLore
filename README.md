# GitLore

**Ask plain-English questions about a Git repository's history — answered by a small AI model running entirely on your own computer.**

> "Why did we change the authentication flow?" → an answer that cites the actual commits and authors.

- 🔒 **100% local & private** — no API keys, no cloud, works offline after the first run
- 💻 **Runs on any ordinary computer** — CPU only, no GPU or compiler needed
- ⚡ **One-click start** — double-click `start.bat` (Windows) or run `./start.sh` (macOS/Linux)

> **Status: working preview.** Indexing, search and chat work end to end on Windows. See [PLAN.md](PLAN.md) for what's next.

## Quick start

Requirements: [Git](https://git-scm.com) and either [uv](https://docs.astral.sh/uv/) (recommended) or Python 3.11–3.13.

```bash
git clone https://github.com/MetehanDemirel/GitLore.git
cd GitLore
./start.sh        # Windows: start.bat
```

The first run installs dependencies and downloads a ~1.1 GB model. Full instructions and troubleshooting: [SETUP.md](SETUP.md).

## How it works

GitLore reads your commit history with GitPython, indexes it for semantic search in ChromaDB,
and answers questions with [Qwen2.5-Coder](https://huggingface.co/Qwen) running locally via llama.cpp,
all behind a Streamlit chat UI. Details: [PLAN.md](PLAN.md).
