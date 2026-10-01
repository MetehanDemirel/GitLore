"""Screenshots, a GIF and real AI answers for the README, from the app itself.

    python scripts/capture_media.py      # needs the model downloaded (data/models) and Playwright's Chromium

Runs a private GitLore (throwaway data folder, the downloaded model linked in, never your projects or chats)
and writes docs/media/*.png, docs/media/ask.gif and docs/media/answers.md.
"""

from __future__ import annotations

import json
import re
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import config  # noqa: E402

OUT = ROOT / "docs" / "media"
SIZE = {"width": 1440, "height": 860}
QUESTIONS = ["Why did we switch login to JWT?", "Why was the CSV export reverted?", "List the security fixes.",
             "What has Priya Nair worked on?", "Why did we add Kubernetes support?"]


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _call(url: str, data: dict | None = None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"null")


def start_server(data: Path) -> tuple[subprocess.Popen, str]:
    (data / "models").mkdir(parents=True)
    shutil.copytree(config.VENDOR_DIR, data / "vendor")
    for model in config.MODELS_DIR.glob("*.gguf"):
        try:
            os.link(model, data / "models" / model.name)  # no 1 GB copy
        except OSError:
            shutil.copy2(model, data / "models" / model.name)
    port = _port()
    env = {**os.environ, "GITLORE_DATA_DIR": str(data), "GITLORE_NO_AUTO_SHUTDOWN": "1", "GITLORE_NO_BROWSER": "1",
           "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "gitlore.py", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(600):
        try:
            state = _call(url + "api/state")
            if state["editor"]["ready"] and state["projects"] and state["projects"][0]["indexed"] > 0:
                assert state["model"]["downloaded"], "download the model in GitLore first"
                return proc, url
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit("GitLore did not start")


def shot(page: Page, name: str) -> None:
    page.wait_for_timeout(600)
    page.screenshot(path=OUT / f"{name}.png")
    print("  ", name)


def ask(page: Page, question: str, frames: list | None = None) -> str:
    page.locator(".assistant button[aria-label='New Chat']").click()
    page.locator("#ask").fill(question)
    page.locator("#ask").press("Enter")
    deadline = time.time() + 240
    while time.time() < deadline:
        if frames is not None:
            frames.append(page.screenshot())
        done = page.evaluate("""() => !!document.querySelector('.messages .answer:not(.caret)')
            && !document.querySelector('.messages .caret, .messages .stage')""")
        if done:
            break
        page.wait_for_timeout(700)
    page.wait_for_timeout(800)
    return page.evaluate("""() => {
        const el = document.querySelectorAll('.messages .answer');
        const answer = el[el.length - 1];  // edited in place: a detached copy would lose its line breaks
        const chips = [...answer.querySelectorAll('[data-hash]')].map((c) => [c, c.textContent]);
        chips.forEach(([c, t]) => { c.textContent = '[' + t.trim() + ']'; });
        const text = answer.innerText;
        chips.forEach(([c, t]) => { c.textContent = t; });
        return text;
    }""")


def to_gif(frames: list[bytes], path: Path) -> None:
    import io
    images = [Image.open(io.BytesIO(f)).convert("RGB") for f in frames]
    images = [im.resize((960, round(im.height * 960 / im.width)), Image.LANCZOS) for im in images]
    # Drop identical consecutive frames, hold the last one.
    kept = [images[0]] + [b for a, b in zip(images, images[1:]) if a.tobytes() != b.tobytes()]
    pal = [im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for im in kept]
    durations = [700] * (len(pal) - 1) + [4000]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix="gitlore-media-"))
    proc, url = start_server(data)
    answers = []
    try:
        _call(url + "api/settings", {"theme": "dark"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport=SIZE, device_scale_factor=1, color_scheme="dark")
            page.goto(url)
            page.wait_for_selector(".commit")
            shot(page, "welcome")

            # The hero GIF: open a commit, ask why, watch the cited answer stream in.
            page.get_by_role("button", name="Open the JWT Login Change").click()
            page.wait_for_selector(".monaco-diff-editor .view-lines", timeout=30000)
            page.wait_for_timeout(1200)
            frames = [page.screenshot()]
            answers.append((QUESTIONS[0], ask(page, QUESTIONS[0], frames)))
            frames += [page.screenshot()]
            to_gif(frames, OUT / "ask.gif")
            print("   ask.gif", len(frames), "frames")
            shot(page, "workspace")

            for q in QUESTIONS[1:]:
                answers.append((q, ask(page, q)))
            shot(page, "answer-trap")

            # Explain buttons on each changed block.
            page.locator(".commit .subject").filter(has_text="Fix SQL injection in search").first.click()
            page.wait_for_selector(".hunk-explain", timeout=30000)
            shot(page, "explain")

            page.get_by_role("button", name="Insights", exact=True).click()
            page.wait_for_selector(".heatmap, svg", timeout=30000)
            shot(page, "insights")
            page.get_by_role("button", name="Contributors").click()
            shot(page, "contributors")
            page.get_by_role("button", name="Releases").click()
            shot(page, "releases")

            page.get_by_role("button", name="Story", exact=True).click()
            page.get_by_role("button", name="Timeline").click()
            page.wait_for_selector(".page .spinner", state="detached", timeout=60000)
            shot(page, "timeline")
            page.get_by_role("button", name="Welcome Brief").click()
            page.get_by_role("button", name="Write Welcome Brief").click()
            page.get_by_text(re.compile(r"^Written (?!by)")).first.wait_for(timeout=300000)
            page.wait_for_timeout(1500)
            shot(page, "onboarding")

            page.keyboard.press("Control+k")
            page.keyboard.press("z")
            shot(page, "zen")
            page.keyboard.press("Escape")

            page.get_by_role("button", name="Settings", exact=True).click()
            page.get_by_role("radio", name="Sepia").click()
            page.wait_for_timeout(600)
            page.screenshot(path=OUT / "themes.png", clip={"x": 0, "y": 0, "width": SIZE["width"], "height": 370})  # no local paths
            browser.close()
    finally:
        proc.terminate()
        proc.wait(10)
        shutil.rmtree(data, ignore_errors=True)

    md = ["# Real answers from GitLore", "",
          f"Recorded with `scripts/capture_media.py` on the demo project, {config.MODEL_PRESETS[config.DEFAULT_PRESET].label}, CPU only.", ""]
    for q, a in answers:
        md += [f"## {q}", "", "> " + a.strip().replace("\n", "\n> "), ""]
    (OUT / "answers.md").write_text("\n".join(md), encoding="utf-8")
    print("done:", OUT)


if __name__ == "__main__":
    main()
