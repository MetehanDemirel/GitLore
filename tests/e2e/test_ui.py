"""Browser tests: a real GitLore server (fresh data folder, fake model) driven with Playwright.

Run: python -m pytest tests/e2e   (needs: python -m playwright install chromium)
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("gitlore-data")
    port = _free_port()
    env = {**os.environ, "GITLORE_DATA_DIR": str(data), "GITLORE_FAKE_LLM": "1",
           "GITLORE_NO_AUTO_SHUTDOWN": "1", "PYTHONIOENCODING": "utf-8"}
    # Git identity for the commit test, without touching the user's real config.
    env |= {"GIT_AUTHOR_NAME": "E2E Tester", "GIT_AUTHOR_EMAIL": "e2e@example.com",
            "GIT_COMMITTER_NAME": "E2E Tester", "GIT_COMMITTER_EMAIL": "e2e@example.com"}
    proc = subprocess.Popen([sys.executable, "gitlore.py", "--no-browser", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 300
    while True:
        assert proc.poll() is None, proc.stdout.read().decode(errors="replace")
        try:
            state = _get(url + "api/state")
            if state["editor"]["ready"] and state["projects"] and state["projects"][0]["indexed"] == 16:
                break
        except OSError:
            pass
        assert time.time() < deadline, "server did not become ready"
        time.sleep(0.5)
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture
def app(server, page: Page):
    page.set_viewport_size({"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(server)
    page.wait_for_selector(".commit")
    yield page
    assert not errors, errors


def open_commit(page: Page, subject: str) -> None:
    # Anchored: "Add CSV export" must not also match 'Revert "Add CSV export"'.
    page.locator(".commit .subject").filter(has_text=re.compile("^" + re.escape(subject))).click()
    page.wait_for_selector(".monaco-diff-editor .view-lines", timeout=30000)
    page.wait_for_timeout(500)


SELECT_LINE_JS = """(text) => {
  const ed = monaco.editor.getDiffEditors()[0].getModifiedEditor();
  const model = ed.getModel();
  const match = model.findMatches(text, false, false, true, null, false)[0];
  if (!match) return null;
  const line = match.range.startLineNumber;
  ed.focus();
  ed.revealLineInCenter(line);
  ed.setSelection(new monaco.Range(line, 1, line, model.getLineMaxColumn(line)));
  const pos = ed.getScrolledVisiblePosition({ lineNumber: line, column: 2 });
  const rect = ed.getDomNode().getBoundingClientRect();
  return { x: rect.left + pos.left, y: rect.top + pos.top, height: pos.height };
}"""


def select_line(page: Page, text: str) -> dict:
    """Select the line containing `text` in the right-hand editor (via Monaco's API, independent of layout)."""
    box = page.evaluate(SELECT_LINE_JS, text)
    assert box, f"no line contains {text!r}"
    page.wait_for_timeout(200)
    return page.evaluate(SELECT_LINE_JS, text)  # measured again after scrolling settled


def context_menu_click(page: Page, box: dict, label: str) -> None:
    for _ in range(5):
        page.mouse.click(box["x"] + 80, box["y"] + box["height"] / 2, button="right")
        item = page.locator(".monaco-menu .action-item", has_text=label).first
        try:
            item.wait_for(state="visible", timeout=2000)
            page.wait_for_timeout(400)  # Monaco ignores clicks that land right after its menu opens
            item.hover()
            item.click()
            return
        except Exception:
            page.keyboard.press("Escape")
    raise AssertionError(f"context menu item {label!r} not found")


def test_first_launch_opens_the_demo_project(app: Page):
    expect(app.locator(".project-switch .name")).to_have_text("TaskFlow (demo)")
    expect(app.locator(".project-switch .tag")).to_have_text("Demo")
    expect(app.locator(".commit")).to_have_count(16)
    expect(app.get_by_role("heading", name="Welcome to GitLore")).to_be_visible()


def test_commit_diff_and_message(app: Page):
    app.get_by_role("button", name="Open the JWT Login Change").click()
    app.wait_for_selector(".monaco-diff-editor .view-lines", timeout=30000)
    expect(app.locator(".commit-message")).to_contain_text("load\nbalancer")
    expect(app.locator(".files .fname")).to_have_text(["taskflow/auth.py"])
    expect(app.locator(".editor.modified .view-lines")).to_contain_text("hmac")
    app.get_by_role("button", name="Inline").click()
    expect(app.get_by_role("button", name="Inline")).to_have_attribute("aria-pressed", "true")


def test_right_click_explain_and_open_citation(app: Page):
    open_commit(app, "Fix overdue filter")
    box = select_line(app, "t.due < today")
    context_menu_click(app, box, "Explain This Change")
    expect(app.locator(".msg.user .bubble").last).to_contain_text("Explain this code")
    expect(app.locator(".msg.user .focus-chip").last).to_contain_text("taskflow/tasks.py")
    cite = app.locator(".messages .answer .cite").last
    expect(cite).to_be_visible(timeout=30000)
    expect(app.locator(".used summary").last).to_contain_text("Used")

    open_commit(app, "Release 1.0")
    cite.click()
    expect(app.locator(".commit[aria-current='true'] .subject")).to_have_text("Fix overdue filter including tasks due today")


def test_theme_toggle_and_language_switch(app: Page):
    html = app.locator("html")
    before = html.get_attribute("data-theme")
    app.locator(".statusbar button", has_text="System").click()
    expect(html).not_to_have_attribute("data-theme", before)

    app.get_by_role("button", name="Settings").click()
    app.get_by_label("Language").select_option("de")
    app.wait_for_selector(".commit")
    expect(app.get_by_role("button", name="Verlauf")).to_be_visible()
    expect(app.locator("html")).to_have_attribute("lang", "de")
    app.get_by_role("button", name="Einstellungen").click()
    app.get_by_label("Sprache").select_option("en")
    app.wait_for_selector(".commit")
    app.get_by_role("button", name="Settings").click()
    app.get_by_role("button", name="System").click()


def test_edit_save_and_commit(app: Page):
    app.get_by_role("button", name="Changes").click()
    app.get_by_role("button", name="Open File…").click()
    app.locator(".palette input").fill("readme")
    app.keyboard.press("Enter")
    app.wait_for_selector(".monaco-diff-editor .view-lines", timeout=30000)
    app.locator(".editor.modified .view-lines").first.click()
    app.keyboard.press("Control+End")
    app.keyboard.type("\nEdited in an end-to-end test.\n")
    app.keyboard.press("Control+s")
    expect(app.locator(".toast")).to_contain_text("Saved")
    expect(app.locator(".sidebar .files .fname")).to_have_text(["README.md"])

    app.get_by_label("Commit message").fill("Document the e2e test")
    app.get_by_role("button", name="Commit 1 File").click()
    expect(app.locator(".toast").last).to_contain_text("Committed")
    expect(app.locator(".sidebar .files .fname")).to_have_count(0)
    app.get_by_role("button", name="History").click()
    expect(app.locator(".commit .subject").first).to_have_text("Document the e2e test")


def test_chats_are_saved_across_reloads(app: Page):
    app.locator(".assistant button[aria-label='New Chat']").click()  # suggestions show in an empty chat
    app.get_by_role("button", name="Why was the CSV export reverted?").click()
    expect(app.locator(".messages .answer .cite").last).to_be_visible(timeout=30000)
    app.reload()
    app.wait_for_selector(".commit")
    expect(app.locator(".assistant .panel-head .btn").first).to_contain_text("Why was the CSV export reverted?")
    expect(app.locator(".msg.user .bubble").first).to_have_text("Why was the CSV export reverted?")


def test_every_button_has_an_accessible_name(app: Page):
    open_commit(app, "Add CSV export")
    unnamed = app.evaluate("""() => [...document.querySelectorAll('button')]
        .filter(b => !b.closest('.monaco-editor') && !(b.getAttribute('aria-label') || b.textContent.trim() || b.title))
        .map(b => b.outerHTML.slice(0, 120))""")
    assert unnamed == []
