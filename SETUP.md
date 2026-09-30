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

**Linux only:** the prebuilt LLM library works only on Alpine, so compile it (needs a C++ compiler, e.g.
`sudo apt install build-essential`; takes about 5 minutes once):
```bash
uv pip install --no-binary-package llama-cpp-python --index-strategy unsafe-best-match -r requirements.txt
```

## Alternative: plain pip

Make sure `python --version` shows 3.11–3.13, then:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt          # Linux: add  --no-binary llama-cpp-python
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
| Answers are slow | Normal on CPU: expect ~5–20 tokens/sec. Lower "commits to index"; the first words take ~10–15 s because the model reads the relevant commits first. |
| macOS + Python 3.13 with uv: "ZIP file contains trailing contents" | That prebuilt file is malformed upstream. Use Python 3.12 (`uv venv --python 3.12`), which the launcher does automatically. |
| Linux: "A C++ compiler is needed" | GitLore compiles its LLM library once on Linux (the prebuilt one only works on Alpine). Install a compiler: `sudo apt install build-essential` (Ubuntu/Debian) or `sudo dnf install gcc-c++` (Fedora), then run `./start.sh` again. |
| Intel Mac: install compiles for a long time | No prebuilt wheel exists for Intel Macs; it builds from source once (needs Xcode Command Line Tools). |

> **GPU?** Not supported out of the box, on purpose, to keep setup simple. Advanced users who
> install a GPU-enabled `llama-cpp-python` themselves get acceleration automatically.
