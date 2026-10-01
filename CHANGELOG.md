# Changelog

## [Unreleased]

### Added
- **Use a model server on your computer.** *Settings → Model → Local Server*: connect GitLore to Ollama,
  LM Studio, llama.cpp's server or anything else with an OpenAI-compatible API (for example
  `http://localhost:11434`), pick one of its models, and answers and stories come from it. Only addresses on
  this computer are accepted, so code still never leaves the machine.

## [0.3.1] — 2026-10-01

### Improved
- **More accurate answers with the same model.** Questions are read for people, files, releases, kinds of
  change and "latest", and the matching commits are found directly instead of by meaning alone; repeated
  look-alike commits are skipped; follow-ups ("Who did that?", "When was it added back?") stay on topic;
  the key instructions are repeated after the question. On a 15-question check against the demo
  (`scripts/eval_answers.py`) correct, cited answers went from 8 to 14.

### Fixed
- Deleting a chat no longer freezes the assistant panel; deleting during an answer stops it.
- Follow-up questions no longer fail when the previous answer used commits.
- After an update, the browser loads the new interface instead of a cached old copy.
- Category chips in the commit list are no longer cut off; the author name gives way instead.

### Docs
- One README instead of README, SETUP and PLAN: what GitLore does, how the AI works, measured quality
  and speed, screenshots and a GIF of the real app (`scripts/capture_media.py` regenerates them).

## [0.3.0] — 2026-09-30

GitLore now explains **why** a project became what it is, helps people who are new or coming back catch
up, and stays calm to look at. This release contains everything planned for v0.3, v0.4 and v0.5.

**Upgrading:** run `start.bat` / `./start.sh` as before. The demo project is rebuilt once (the old one is
replaced automatically); your own projects, chats and model are kept.

### Calm workspace
- Hide the sidebar (**Ctrl+B**, or click the active view's icon) and the assistant (**Ctrl+Alt+B**).
- **Zen mode** (**Ctrl+K Z**, **Esc** to leave): only the editor, or only the chat (*Focus Chat*).
- Nine color themes: System, Light, Dark, Dim, Solarized Light/Dark, Sepia, and High Contrast Light/Dark,
  all checked against WCAG contrast. The code editor follows the theme.
- **Explain Commit** button in the commit header, and a small **Explain** action on every changed block
  of a diff (no right-click needed).

### A bigger demo
- TaskFlow now has ~2 years of history: 189 commits by 8 fictional contributors, releases v1.0.0 → v2.2.1,
  feature branches and merges, a package restructure, a security fix, a performance fix, reverts and
  issue references. Still generated in a fraction of a second, identical on every computer.

### Insights (instant, no AI)
- Commit **categories** (feature, bug fix, refactor, performance, security, docs, tests, dependencies,
  large change) as chips and search filters.
- Overview with a **commit heatmap** and monthly activity, **contributors** and minimal profiles,
  **hot files**, **"who wrote this?"** (blame), a **release explorer**, **branches** and **compare**.
- **Advanced search:** `author:` `path:` `type:` `since:` `until:` `release:` `is:large`, plus words.

### The story of a repository (AI, cached)
- **Generate Repository History:** a cited narrative of the project, era by era (by release).
- **Timeline** of key events; click an event for its commits, or ask the AI why it happened.
- **What Changed While I Was Away?** — since your last visit or any date.
- **Onboarding brief** for newcomers: the project in a page, key people, where to start reading.
- Answers **dig for why**: related commits (same issue number, reverts) are added to the evidence, and
  citations of commits that don't exist are removed.

### Online mode (optional)
- Add a public GitHub repository by URL (`github.com/owner/repo`). GitLore makes a shallow clone
  (newest 1,000 commits), keeps it up to date while open, and shows the **pull requests and issues behind
  a commit**, GitHub releases and repository info. Online projects are read-only mirrors.
- No sign-in and nothing stored: anonymous requests (60/hour, cached). A `GITHUB_TOKEN` environment
  variable raises the limit. Private repositories are not supported yet.

### Languages
- Answers can now be in Spanish, Italian and Chinese too. **UI translations** for these three, and for
  the new v0.3 screens in Turkish, French and German, are still to come; those texts show in English.

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
