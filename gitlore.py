"""Start GitLore: python gitlore.py [--port N] [--no-browser]

Serves the web UI on 127.0.0.1, opens it in the browser, and exits by itself ~30 s after the last
tab is closed (set GITLORE_NO_AUTO_SHUTDOWN=1 to keep it running).
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from src import config
from src.server import HEARTBEAT, create_app


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind((config.HOST, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"[GitLore] No free port between {preferred} and {preferred + 19}.")


def open_when_ready(url: str) -> None:
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "api/health", timeout=1)
            webbrowser.open(url)
            return
        except OSError:
            time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser(description="GitLore: ask questions about your Git history.")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--no-browser", action="store_true", default=bool(os.environ.get("GITLORE_NO_BROWSER")))
    args = parser.parse_args()

    print("[GitLore] Preparing (the first launch creates the demo project)…", flush=True)
    app = create_app()
    port = free_port(args.port)
    url = f"http://{config.HOST}:{port}/"
    print(f"[GitLore] Running at {url}  — close the browser tab (or this window) to stop.", flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    if not os.environ.get("GITLORE_NO_AUTO_SHUTDOWN"):
        threading.Thread(target=HEARTBEAT.watch, name="gitlore-idle-shutdown", daemon=True).start()
    uvicorn.run(app, host=config.HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
