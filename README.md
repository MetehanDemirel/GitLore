# GitLore

[![CI](https://github.com/MetehanDemirel/GitLore/actions/workflows/ci.yml/badge.svg)](https://github.com/MetehanDemirel/GitLore/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Ask plain-English questions about a Git repository's history — answered by a small AI model running entirely on your own computer.**

> "Why did we change the authentication flow?" → an answer that cites the actual commits and authors.

- **100% local & private** — no API keys, no cloud, works offline after the first run
- **Runs on any ordinary computer** — CPU only, no GPU needed (Linux compiles one library on first install)
- **One-click start** — double-click `start.bat` (Windows) or run `./start.sh` (macOS/Linux)

> **Status: v0.3.0.** A calm, VS Code-like workspace for Git history: colored diffs, one-click "Explain", instant insights (categories, heatmap, contributors, releases, search), AI-written repository history, timeline, "what changed while I was away" and onboarding briefs, and an optional online mode for public GitHub repositories. See [CHANGELOG.md](CHANGELOG.md).

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
and answers questions with [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B) running locally via llama.cpp,
all in a VS Code-like browser workspace built on Monaco. Details: [PLAN.md](PLAN.md).

## Roadmap

v0.3 (released) contains everything planned for v0.3–v0.5. Next:

- UI translations for Spanish, Italian and Chinese, and for the new screens in Turkish, French and German.
- Private GitHub repositories (sign-in) — an open decision.
- Saved searches.

Details and open decisions: [PLAN.md](PLAN.md#v03-and-beyond--roadmap-planned-2026-09-30).
