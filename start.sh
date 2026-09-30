#!/usr/bin/env bash
# GitLore launcher (macOS / Linux). First run creates .venv and installs dependencies;
# later runs start instantly. Press Ctrl+C or close the browser tab to stop.
set -euo pipefail
cd "$(dirname "$0")"
VENV_PY=".venv/bin/python"

fail() { echo "[GitLore] $1"; echo "[GitLore] See SETUP.md for troubleshooting."; exit 1; }

command -v git >/dev/null || fail "Git is not installed or not on PATH."
HAS_UV=0; command -v uv >/dev/null && HAS_UV=1

# 1. Create the virtual environment (Python 3.11-3.13; 3.14 is not supported)
if [ ! -x "$VENV_PY" ]; then
    echo "[GitLore] Creating virtual environment..."
    if [ "$HAS_UV" = 1 ]; then
        uv venv --python 3.12 .venv
    else
        PY=""
        for v in 3.12 3.13 3.11; do
            if command -v "python$v" >/dev/null; then PY="python$v"; break; fi
        done
        [ -n "$PY" ] || fail "Need Python 3.11-3.13 or uv. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        "$PY" -m venv .venv
    fi
fi

# 2. Install dependencies only when requirements.txt changed
if ! cmp -s requirements.txt .venv/requirements.stamp; then
    echo "[GitLore] Installing dependencies (first run takes a few minutes)..."
    if [ "$HAS_UV" = 1 ]; then
        uv pip install --python "$VENV_PY" -r requirements.txt
    else
        "$VENV_PY" -m pip install --disable-pip-version-check -r requirements.txt
    fi
    cp requirements.txt .venv/requirements.stamp
fi

# 3. Run
echo "[GitLore] Starting... a browser tab will open."
exec "$VENV_PY" -m streamlit run app.py "$@"
