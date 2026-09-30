# Changelog

## [0.2.1] — 2026-09-30

Supersedes 0.2.0: the same workspace, now fully verified.

### Fixed
- Browser tests are no longer marked "known-flaky": both failures were in the tests, not the app.
  Monaco's context menu deliberately ignores a click that lands right after it opens (so the
  right-click release can't trigger an item); the tests now pause like a person would, select code
  through Monaco's API instead of by mouse position, and match commit titles exactly.
- CI runs the browser tests (Chromium) on every push, alongside the Windows/macOS/Linux tests and
  launcher checks.

## [0.2.0] — 2026-09-30

GitLore is now a small **VS Code-like workspace for Git history**, with a built-in demo project to try
everything immediately.

**Upgrading from 0.1:** download the new version and run `start.bat` / `./start.sh` as before. The first
launch downloads the code editor (Monaco, ~19 MB, one time). Your downloaded model is reused.

### Features
- New interface: activity bar, commit timeline with author colors, side-by-side or inline colored diffs
  (Monaco, VS Code's editor), full commit messages, resizable panels, status bar.
- **Built-in demo project** "TaskFlow" with a meaningful history, open on first launch.
- **Ask about code**: select code in a diff, right-click, choose *Ask GitLore About Selection* or
  *Explain This Change*. Citations in answers are clickable and open the commit.
- **Edit and commit**: open any file, edit it in the diff view (Ctrl+S saves), and commit selected files
  as a new commit. History is never rewritten; unsafe states (detached HEAD, merges) are refused.
- **Projects and chats are saved**: switch between repositories; chats per project, rename and delete.
- **Languages**: English, Turkish, French and German, for the interface, the editor's menus and the
  assistant's answers.
- **Themes**: light, dark, or follow the system.
- Lighter install: Streamlit removed (~180 MB less).

### Known limitations
- Answers take ~10–25 s to start on a laptop CPU. Turkish answers from the small model are understandable
  but sometimes use an awkward word.

## [0.1.0] — 2026-09-30

First public release. Ask plain-English questions about a Git repository's history and get answers
that cite the commits they come from — fully local, CPU-only, no API keys.

**Getting started:** download the source below (or `git clone`), then double-click `start.bat` (Windows)
or run `./start.sh` (macOS / Linux). Needs Git and either [uv](https://docs.astral.sh/uv/) or Python 3.11–3.13.
See [SETUP.md](https://github.com/MetehanDemirel/GitLore/blob/main/SETUP.md).

### Features
- One-click launchers that create an isolated environment and install everything — no GPU or Docker needed (Linux compiles the LLM library once; needs a C++ compiler).
- Side panel to download the model (Qwen3-1.7B, 1.1 GB, one time) and index any local repository with live progress.
- Chat with streamed answers, a stop button, commit citations linked to GitHub/GitLab, and the commits each answer used.
- Fast history reading: 2,000 commits parse in under a second; merge commits carry their pull request's changes.
- Semantic search plus exact commit-hash lookup; only new commits are indexed on updates.
- Private by design: runs on your machine, telemetry off, closes itself ~30 s after the browser tab is closed.

### Known limitations
- Answers take ~10–15 s to start on a typical laptop CPU (the model reads the relevant commits first).
- Intel Macs build the LLM library from source on first install (needs Xcode Command Line Tools).
- Python 3.14 is not supported yet.
