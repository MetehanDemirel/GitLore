# Changelog

## [0.1.0] — 2026-09-30

First public release. Ask plain-English questions about a Git repository's history and get answers
that cite the commits they come from — fully local, CPU-only, no API keys.

**Getting started:** download the source below (or `git clone`), then double-click `start.bat` (Windows)
or run `./start.sh` (macOS / Linux). Needs Git and either [uv](https://docs.astral.sh/uv/) or Python 3.11–3.13.
See [SETUP.md](https://github.com/MetehanDemirel/GitLore/blob/main/SETUP.md).

### Features
- One-click launchers that create an isolated environment and install everything — no compiler, GPU or Docker needed.
- Side panel to download the model (Qwen3-1.7B, 1.1 GB, one time) and index any local repository with live progress.
- Chat with streamed answers, a stop button, commit citations linked to GitHub/GitLab, and the commits each answer used.
- Fast history reading: 2,000 commits parse in under a second; merge commits carry their pull request's changes.
- Semantic search plus exact commit-hash lookup; only new commits are indexed on updates.
- Private by design: runs on your machine, telemetry off, closes itself ~30 s after the browser tab is closed.

### Known limitations
- Answers take ~10–15 s to start on a typical laptop CPU (the model reads the relevant commits first).
- Intel Macs build the LLM library from source on first install (needs Xcode Command Line Tools).
- Python 3.14 is not supported yet.
