# GitLore — Setup Guide

GitLore runs 100% locally on your CPU. No GPU, compiler, Docker, Ollama, or API keys needed.

## Requirements

- **Python 3.11, 3.12 or 3.13** (3.12 recommended). ⚠️ Python 3.14 does **not** work yet — the LLM library has no prebuilt build for it.
- **Git** installed and on PATH (`git --version` should work).
- ~4 GB free disk (≈1.1 GB model + ≈80 MB embedder + ≈1 GB of Python packages) and 8 GB RAM recommended.
- Internet on **first run only** (downloads the model). Fully offline afterwards.

## Easiest: one-click launcher

- **Windows:** double-click `start.bat`
- **macOS / Linux:** `./start.sh`

The first run creates a `.venv` and installs everything (a few minutes); later runs start in seconds.
The launcher uses [uv](https://docs.astral.sh/uv/) if installed, otherwise an existing Python 3.11–3.13.

## Manual install (recommended: uv)

[uv](https://docs.astral.sh/uv/) installs the right Python for you, even if your system has 3.14.

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # once
uv venv --python 3.12
.venv\Scripts\activate
uv pip install -r requirements.txt
streamlit run app.py
```

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # once
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
streamlit run app.py
```

## Alternative: plain pip

Make sure `python --version` shows 3.11–3.13, then:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## First run

1. A browser tab opens at `http://127.0.0.1:8501`.
2. In the side panel, click **Download Model** (~1.1 GB, saved in `data/models/`) — one time only.
3. Paste the path to a local Git repository and click **Index Repository**.
4. Ask questions like *"Why was the auth flow changed?"* or *"Who introduced the caching layer?"*

**To stop:** close the browser tab (the app exits by itself after ~30 s) or close the terminal window.

## Uninstall / free disk space

Delete the project folder. The embedding model is cached separately in `~/.cache/chroma/` — delete that too if you want.

## Troubleshooting

| Problem | Fix |
|---|---|
| `llama-cpp-python` tries to compile / "CMake" or "cl.exe not found" errors | You're on an unsupported Python (usually 3.14) or didn't use `requirements.txt` (it contains the prebuilt-wheel index). Use `uv venv --python 3.12`. |
| `tokenizers` build error mentioning Rust/cargo | You installed packages without `requirements.txt`'s `huggingface-hub<2` cap. Reinstall from `requirements.txt`. |
| "git not found" | Install Git and reopen the terminal. |
| Answers are slow | Normal on CPU: expect ~5–20 tokens/sec. Lower "commits to index" or use the default 1.5B model. |
| Intel Mac: install compiles for a long time | No prebuilt wheel exists for Intel Macs; it builds from source once (needs Xcode Command Line Tools). |

> **GPU?** Not supported out of the box, on purpose, to keep setup simple. Advanced users who
> install a GPU-enabled `llama-cpp-python` themselves get acceleration automatically.
