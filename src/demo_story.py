"""The later eras of the TaskFlow demo (after 1.0): hand-written key commits plus seeded filler work.

Kept separate from src/demo.py, which holds era 1 and the builder, so the story reads top to bottom.
Everything here is fictional: people, emails and issue numbers.
"""

from __future__ import annotations

import random

AUTHORS_LATER = {
    "mina": ("Mina Chen", "mina@taskflow.example"),
    "omar": ("Omar Haddad", "omar@taskflow.example"),
    "jonas": ("Jonas Weber", "jonas@taskflow.example"),
    "priya": ("Priya Nair", "priya@taskflow.example"),
    "lucia": ("Lucía Romero", "lucia@taskflow.example"),
}

# ------------------------------------------------------------------ file contents used by key commits
STORAGE_TAGS = '''"""Save and load tasks in SQLite."""

import sqlite3
from pathlib import Path

from taskflow.models import Task

DB_FILE = Path.home() / ".taskflow.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT, done INTEGER, "
        "due TEXT, priority INTEGER, tags TEXT DEFAULT '')"
    )
    return conn


def save(tasks: list[Task]) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM tasks")
        conn.executemany(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?)",
            [(t.id, t.title, int(t.done), t.due and t.due.isoformat(), t.priority, ",".join(t.tags)) for t in tasks],
        )


def load() -> list[Task]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, title, done, due, priority, tags FROM tasks").fetchall()
    return [Task(id=r[0], title=r[1], done=bool(r[2]), due=r[3], priority=r[4], tags=[x for x in r[5].split(",") if x])
            for r in rows]
'''

SEARCH_UNSAFE = '''

def search(term: str) -> list[Task]:
    """Tasks whose title contains `term`."""
    with _connect() as conn:
        rows = conn.execute(f"SELECT id, title, done, due, priority, tags FROM tasks WHERE title LIKE '%{term}%'").fetchall()
    return [Task(id=r[0], title=r[1], done=bool(r[2]), due=r[3], priority=r[4], tags=[x for x in r[5].split(",") if x])
            for r in rows]
'''

SEARCH_SAFE = SEARCH_UNSAFE.replace(
    '''rows = conn.execute(f"SELECT id, title, done, due, priority, tags FROM tasks WHERE title LIKE '%{term}%'").fetchall()''',
    '''rows = conn.execute(
            "SELECT id, title, done, due, priority, tags FROM tasks WHERE title LIKE ?", (f"%{term}%",)
        ).fetchall()''',
)

INDEX_BLOCK = '''    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_open_due ON tasks (done, due)")
'''

RECURRING = '''"""Recurring tasks: when one is completed, the next occurrence is created."""

from datetime import date, timedelta

from taskflow.models import Task

INTERVALS = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}


def next_due(due: date, every: str) -> date:
    if every == "monthly":
        month = due.month % 12 + 1
        return due.replace(year=due.year + (due.month == 12), month=month, day=min(due.day, 28))
    return due + INTERVALS[every]
'''

RECURRING_DONE = RECURRING + '''

def complete(tasks: list[Task], task: Task, every: str | None) -> Task | None:
    """Mark `task` done and, for recurring tasks, add the next occurrence."""
    task.done = True
    if not every or task.due is None:
        return None
    follow_up = Task(id=len(tasks) + 1, title=task.title, due=next_due(task.due, every), priority=task.priority)
    tasks.append(follow_up)
    return follow_up
'''

API = '''"""A small REST API using only the standard library."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from taskflow import storage


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/tasks":
            body = json.dumps([t.__dict__ for t in storage.load()], default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)


def serve(port: int = 8080) -> None:
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
'''

API_AUTH = API.replace(
    "from taskflow import storage\n",
    "from taskflow import auth, storage\n",
).replace(
    '''    def do_GET(self):
        if self.path == "/tasks":''',
    '''    def do_GET(self):
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if auth.current_user(token) is None:
            self.send_error(401, "Missing or invalid token")
            return
        if self.path == "/tasks":''',
)

CLI_COLOR = '''"""Command-line interface with colored output."""

import sys

from taskflow import storage

RESET, RED, YELLOW, DIM = "\\033[0m", "\\033[31m", "\\033[33m", "\\033[2m"
COLORS = {1: RED, 2: "", 3: DIM}


def color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if code and sys.stdout.isatty() else text


def show() -> None:
    for task in storage.load():
        print(color(f"[{task.id}] {task.title}", COLORS.get(task.priority, "")))
'''

TZ_FIX_OLD = "def overdue(tasks: list[Task], today: date) -> list[Task]:"
TZ_FIX_NEW = '''def local_today() -> date:
    """Today in the user's time zone (date.today() used UTC on servers, shifting due dates by a day)."""
    from datetime import datetime
    return datetime.now().astimezone().date()


def overdue(tasks: list[Task], today: date) -> list[Task]:'''

CI_YML = '''name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install pytest && pytest
'''

PLUGINS = '''"""Plugins: third-party packages can add CLI commands.

A plugin exposes a `register(commands)` function via the "taskflow.plugins" entry point.
"""

from importlib.metadata import entry_points


def load_commands() -> dict:
    commands: dict = {}
    for ep in entry_points(group="taskflow.plugins"):
        ep.load()(commands)
    return commands
'''

CACHE = '''"""In-memory cache of the task list for the API.

Loading every task from SQLite on each request made the API slow for large accounts (#58);
responses are ~5x faster with this cache, which is cleared on every write.
"""

from taskflow.core import storage

_cache = None


def tasks():
    global _cache
    if _cache is None:
        _cache = storage.load()
    return _cache


def invalidate() -> None:
    global _cache
    _cache = None
'''

RATE_LIMIT = '''"""Login rate limiting: at most 5 failed attempts per user per 15 minutes."""

import time

WINDOW = 15 * 60
MAX_FAILURES = 5
_failures: dict[str, list[float]] = {}


def allowed(username: str) -> bool:
    recent = [t for t in _failures.get(username, []) if time.time() - t < WINDOW]
    _failures[username] = recent
    return len(recent) < MAX_FAILURES


def record_failure(username: str) -> None:
    _failures.setdefault(username, []).append(time.time())
'''

DASHBOARD = '''<!doctype html>
<title>TaskFlow</title>
<h1>TaskFlow</h1>
<ul id="tasks"></ul>
<script>
fetch("/tasks").then(r => r.json()).then(tasks => {
  for (const t of tasks) {
    const li = document.createElement("li");
    li.textContent = t.title;
    document.getElementById("tasks").appendChild(li);
  }
});
</script>
'''

DASHBOARD_PAGED = DASHBOARD.replace('fetch("/tasks")', 'fetch("/tasks?page=1&per_page=50")')

PAGINATION = '''

def paginate(items: list, page: int = 1, per_page: int = 50) -> dict:
    """Slice a list for the API; large accounts no longer load everything at once."""
    start = (max(page, 1) - 1) * per_page
    return {"items": items[start:start + per_page], "page": page, "total": len(items)}
'''

I18N = '''"""Translated CLI messages."""

MESSAGES = {
    "en": {"added": "Task added", "none": "No tasks"},
    "es": {"added": "Tarea añadida", "none": "No hay tareas"},
    "tr": {"added": "Görev eklendi", "none": "Görev yok"},
}


def message(key: str, lang: str = "en") -> str:
    return MESSAGES.get(lang, MESSAGES["en"]).get(key, MESSAGES["en"][key])
'''

REMINDERS = '''"""Email reminders for tasks that are due tomorrow."""

import smtplib
from datetime import timedelta
from email.message import EmailMessage

from taskflow.core.models import local_today


def due_tomorrow(tasks):
    tomorrow = local_today() + timedelta(days=1)
    return [t for t in tasks if not t.done and t.due == tomorrow]


def send(address: str, tasks) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"{len(tasks)} tasks due tomorrow"
    msg["To"] = address
    msg.set_content("\\n".join(t.title for t in tasks))
    with smtplib.SMTP("localhost") as smtp:
        smtp.send_message(msg)
'''

REMINDERS_DST = REMINDERS.replace(
    '''def due_tomorrow(tasks):
    tomorrow = local_today() + timedelta(days=1)
    return [t for t in tasks if not t.done and t.due == tomorrow]''',
    '''_sent: set[tuple[int, str]] = set()


def due_tomorrow(tasks):
    """Tasks due tomorrow that haven't been reminded yet.

    On the daylight-saving change the scheduler ran twice in the same local hour and sent every
    reminder twice (#97); remembering (task, date) pairs makes sending idempotent.
    """
    tomorrow = local_today() + timedelta(days=1)
    due = [t for t in tasks if not t.done and t.due == tomorrow and (t.id, str(tomorrow)) not in _sent]
    _sent.update((t.id, str(tomorrow)) for t in due)
    return due''',
)

FTS = '''

def search_fast(term: str) -> list[int]:
    """Full-text search using SQLite FTS5: ~100x faster than LIKE on 100k tasks (#88)."""
    with _connect() as conn:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(title, content='tasks', content_rowid='id')")
        return [r[0] for r in conn.execute("SELECT rowid FROM tasks_fts WHERE tasks_fts MATCH ?", (term,))]
'''

EXPORT_FIXED = '''"""Export tasks to CSV (works the same on Windows, macOS and Linux)."""

import csv
from pathlib import Path


def export_csv(tasks, path: Path) -> None:
    # newline="" lets the csv module write \\r\\n itself; without it Windows got blank lines (see the 2025 revert).
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "title", "done", "due", "priority"])
        for t in tasks:
            writer.writerow([t.id, t.title, t.done, t.due, t.priority])
'''

SHORTCUTS = '''<script>
// Keyboard shortcuts: n = new task, / = search, ? = help
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.key === "n") document.getElementById("new-task")?.focus();
  if (e.key === "/") { e.preventDefault(); document.getElementById("search")?.focus(); }
});
</script>
'''

REFRESH_FIX_OLD = '''def refresh(token: str) -> str | None:
    """Issue a fresh token for a still-valid one, so active users are not logged out mid-task."""
    user = current_user(token)'''
REFRESH_FIX_NEW = '''_decoded: dict[str, str] = {}  # token -> user; never trusted without the expiry check


def refresh(token: str) -> str | None:
    """Issue a fresh token for a still-valid one, so active users are not logged out mid-task.

    Always re-validate: an earlier version looked the user up in a cache of decoded tokens and
    skipped the expiry check, so an expired token could be refreshed forever (#104).
    """
    user = current_user(token)
    _decoded.pop(token, None)'''

# ------------------------------------------------------------------ key commits after 1.0
# Steps use the same vocabulary as src/demo.py STEPS, plus:
#   ("edit", author, date, message, {path: ("append"|"replace"|"set"|"delete", ...)})
#   ("tag", name, author, date, message)
KEY_STEPS: list[tuple] = [
    ("edit", "mina", "2025-04-02T10:20:00+02:00",
     "Add tags to tasks\n\nPeople asked to group tasks by project or context (#21). Tags are stored as a\n"
     "comma-separated column so existing databases keep working.",
     {"taskflow/models.py": [("replace", "from dataclasses import dataclass\n", "from dataclasses import dataclass, field\n"),
                             ("replace", "    priority: int = 2  # 1 = high, 2 = normal, 3 = low\n",
                              "    priority: int = 2  # 1 = high, 2 = normal, 3 = low\n    tags: list[str] = field(default_factory=list)\n")],
      "taskflow/storage.py": ("set", STORAGE_TAGS)}),
    ("edit", "mina", "2025-04-07T15:05:00+02:00",
     "Add search command\n\nSearch task titles from the CLI: taskflow search <term> (#24).",
     {"taskflow/storage.py": ("append", SEARCH_UNSAFE)}),
    ("edit", "omar", "2025-04-15T09:30:00+02:00",
     "Speed up task listing with an index on (done, due)\n\nListing 10,000 tasks took 1.8 s because SQLite scanned the whole table for\n"
     "every overdue check (#27). An index on (done, due) brings it down to about 40 ms.",
     {"taskflow/storage.py": ("replace", "    return conn\n", INDEX_BLOCK + "    return conn\n")}),
    ("tag", "v1.1.0", "ada", "2025-04-22T12:00:00+02:00",
     "TaskFlow 1.1\n\n- Tags on tasks (#21)\n- Search (#24)\n- Much faster listing for large task lists (#27)"),
    ("edit", "omar", "2025-05-05T18:40:00+02:00",
     "Fix SQL injection in search\n\nSecurity report #31: search built its SQL with an f-string, so a term like\n"
     "`' OR 1=1 --` returned every task in the database, including other users'.\n"
     "The term is now passed as a query parameter.",
     {"taskflow/storage.py": ("replace", SEARCH_UNSAFE, SEARCH_SAFE)}),
    ("tag", "v1.1.1", "omar", "2025-05-06T09:00:00+02:00",
     "TaskFlow 1.1.1 (security release)\n\nFixes an SQL injection in search (#31). Everyone on 1.1.0 should upgrade."),
    ("branch", "sara/recurring"),
    ("edit", "sara", "2025-05-20T11:10:00+02:00",
     "Add recurring tasks (daily, weekly, monthly)\n\nRequested by many users (#33). Monthly tasks due on the 29th-31st move to\n"
     "the 28th so they exist in every month.",
     {"taskflow/recurring.py": ("set", RECURRING)}),
    ("edit", "sara", "2025-05-22T16:45:00+02:00",
     "Create the next occurrence when a recurring task is done",
     {"taskflow/recurring.py": ("set", RECURRING_DONE)}),
    ("checkout", "main"),
    ("merge", "ada", "2025-05-26T10:00:00+02:00", "sara/recurring",
     "Merge pull request #35 from sara/recurring\n\nRecurring tasks"),
    ("edit", "leo", "2025-06-12T13:25:00+02:00",
     "Add a REST API using only the standard library\n\nLets the new mobile app read tasks (#38). Built on http.server to avoid\n"
     "adding a web framework dependency for three endpoints.",
     {"taskflow/api.py": ("set", API)}),
    ("edit", "leo", "2025-06-20T10:05:00+02:00",
     "Require a valid token on every API endpoint\n\nThe first API version answered /tasks without authentication, so anyone\n"
     "on the network could read everyone's tasks. Every request now needs a Bearer token.",
     {"taskflow/api.py": ("set", API_AUTH)}),
    ("tag", "v1.2.0", "ada", "2025-07-01T12:00:00+02:00",
     "TaskFlow 1.2\n\n- Recurring tasks (#33)\n- REST API for the mobile app (#38), token-protected"),
    ("edit", "mina", "2025-07-15T14:30:00+02:00",
     "Colorize CLI output by priority\n\nHigh-priority tasks show in red, low ones dimmed. Colors are skipped when the\n"
     "output isn't a terminal, so scripts and pipes still get plain text.",
     {"taskflow/cli.py": ("set", CLI_COLOR)}),
    ("edit", "ada", "2025-07-28T09:15:00+02:00",
     "Fix due dates shifting by one day for users west of UTC\n\nThe server computed \"today\" in UTC, so in the evening in the Americas tasks\n"
     "showed as overdue a day early (#44). Use the user's local date instead.",
     {"taskflow/models.py": ("replace", TZ_FIX_OLD, TZ_FIX_NEW)}),
    ("tag", "v1.3.0", "ada", "2025-08-05T12:00:00+02:00",
     "TaskFlow 1.3\n\n- Colored CLI output\n- Fix: due dates shifted for users west of UTC (#44)"),
    ("edit", "jonas", "2025-08-20T11:00:00+02:00",
     "ci: run the test suite on every push\n\nWe shipped two regressions in 1.3 that the existing tests would have caught.",
     {".github/workflows/ci.yml": ("set", CI_YML)}),
    ("restructure", "priya", "2025-09-02T16:20:00+02:00",
     "refactor: split into core, api and cli packages\n\nThe flat module layout mixed storage, HTTP and terminal code, and every new\n"
     "feature touched five files at the top level (#52). Code now lives in three\n"
     "packages with one-way dependencies: cli and api use core, never each other.\n\n"
     "BREAKING CHANGE: imports moved, e.g. taskflow.storage -> taskflow.core.storage.",
     {"taskflow/models.py": "taskflow/core/models.py", "taskflow/storage.py": "taskflow/core/storage.py",
      "taskflow/auth.py": "taskflow/core/auth.py", "taskflow/recurring.py": "taskflow/core/recurring.py",
      "taskflow/api.py": "taskflow/api/server.py", "taskflow/cli.py": "taskflow/cli/main.py"},
     {"taskflow.models": "taskflow.core.models", "taskflow.storage": "taskflow.core.storage",
      "from taskflow import auth, storage": "from taskflow.core import auth, storage",
      "from taskflow import storage": "from taskflow.core import storage"}),
    ("edit", "leo", "2025-09-10T17:00:00+02:00",
     "Hand over ownership of the auth code to Priya\n\nI'm moving to another team; Priya reviewed every auth change this year.",
     {"CODEOWNERS": ("set", "taskflow/core/auth.py @priya\ntaskflow/api/ @jonas @priya\n")}),
    ("edit", "jonas", "2025-09-25T10:40:00+02:00",
     "feat: plugin system for custom commands\n\nTeams kept forking TaskFlow to add one command (#55). Plugins register\n"
     "commands through the \"taskflow.plugins\" entry point instead.",
     {"taskflow/plugins.py": ("set", PLUGINS)}),
    ("edit", "priya", "2025-10-08T15:15:00+02:00",
     "perf: cache the task list in memory for the API\n\nThe API loaded every task from SQLite on each request; large accounts waited\n"
     "over a second per page (#58). Responses are about 5x faster with a cache that\n"
     "is cleared on every write.",
     {"taskflow/api/cache.py": ("set", CACHE)}),
    ("edit", "priya", "2025-10-20T11:50:00+02:00",
     "security: rate-limit failed logins\n\nWe saw password-guessing attempts in the logs (#61): thousands of logins per\n"
     "minute against a few accounts. At most 5 failures per user per 15 minutes.",
     {"taskflow/core/ratelimit.py": ("set", RATE_LIMIT)}),
    ("edit", "mina", "2025-11-03T14:00:00+01:00",
     "Add a web dashboard\n\nA read-only page listing your tasks, served by the API (#64).",
     {"taskflow/api/static/dashboard.html": ("set", DASHBOARD)}),
    ("revert", "mina", "2025-11-10T09:30:00+01:00",
     'Revert "Add a web dashboard"\n\nIt loaded the full task list on every page view and timed out for accounts\n'
     "with more than ~20,000 tasks. Bringing it back after the API has pagination."),
    ("edit", "jonas", "2025-11-25T16:10:00+01:00",
     "feat(api): paginate task lists\n\nNeeded for the dashboard and for large accounts (#66). 50 items per page.",
     {"taskflow/api/server.py": ("append", PAGINATION)}),
    ("edit", "mina", "2025-12-04T11:20:00+01:00",
     "Bring back the web dashboard, now paginated\n\nSame page as the reverted version, but it loads 50 tasks at a time.",
     {"taskflow/api/static/dashboard.html": ("set", DASHBOARD_PAGED)}),
    ("tag", "v2.0.0", "priya", "2025-12-15T12:00:00+01:00",
     "TaskFlow 2.0\n\nBreaking: the package layout changed (core / api / cli). See the migration notes.\n\n"
     "- Plugin system (#55)\n- API: pagination (#66), in-memory cache (#58)\n- Web dashboard\n"
     "- Security: login rate limiting (#61)"),
    ("edit", "lucia", "2026-01-12T10:00:00+01:00",
     "Translate CLI messages into Spanish and Turkish\n\nFirst step towards a translated TaskFlow (#71).",
     {"taskflow/cli/i18n.py": ("set", I18N)}),
    ("edit", "sara", "2026-02-03T15:30:00+01:00",
     "Add email reminders for tasks due tomorrow\n\nThe most requested feature of 2025 (#74). Runs daily from cron.",
     {"taskflow/core/reminders.py": ("set", REMINDERS)}),
    ("edit", "omar", "2026-04-09T13:45:00+02:00",
     "perf: full-text search with SQLite FTS5\n\nSearch with LIKE took 2-3 s on accounts with 100,000 tasks (#88). FTS5 answers\n"
     "the same queries in about 20 ms.",
     {"taskflow/core/storage.py": ("append", FTS)}),
    ("tag", "v2.1.0", "priya", "2026-04-20T12:00:00+02:00",
     "TaskFlow 2.1\n\n- Email reminders (#74)\n- Spanish and Turkish CLI (#71)\n- Much faster search (#88)"),
    ("edit", "ada", "2026-07-01T09:40:00+02:00",
     "Fix reminders sent twice after the daylight saving change\n\nOn the night the clocks moved, the scheduler ran twice in the same local hour\n"
     "and every reminder went out twice (#97). Sending is now idempotent per task and day.",
     {"taskflow/core/reminders.py": ("set", REMINDERS_DST)}),
    ("tag", "v2.2.0", "priya", "2026-07-15T12:00:00+02:00",
     "TaskFlow 2.2\n\n- Fix: duplicate reminders after the DST change (#97)\n- Dependency updates"),
    ("edit", "priya", "2026-09-03T17:25:00+02:00",
     "security: refresh() must reject expired tokens\n\nrefresh() reused a cached decode that skipped the expiry check, so an expired\n"
     "token could be refreshed forever (#104). Reported privately by a user.",
     {"taskflow/core/auth.py": ("replace", REFRESH_FIX_OLD, REFRESH_FIX_NEW)}),
    ("tag", "v2.2.1", "priya", "2026-09-04T10:00:00+02:00",
     "TaskFlow 2.2.1 (security release)\n\nExpired tokens could be refreshed (#104). Please upgrade."),
    ("edit", "lucia", "2026-09-20T14:10:00+02:00",
     "Add CSV export again, now safe on Windows\n\nThe 2025 version was reverted because Windows got blank lines between rows.\n"
     "Opening the file with newline=\"\" fixes it; tested on all three platforms (#109).",
     {"taskflow/core/export.py": ("set", EXPORT_FIXED)}),
    ("edit", "mina", "2026-09-25T11:30:00+02:00",
     "Add keyboard shortcuts to the dashboard\n\nn: new task, /: search (#110).",
     {"taskflow/api/static/dashboard.html": ("append", SHORTCUTS)}),
    # Branches still open at the end, for the branch view.
    ("branch", "experiment/graphql"),
    ("edit", "jonas", "2026-08-28T16:00:00+02:00",
     "wip: GraphQL endpoint experiment\n\nExploring whether the mobile app would benefit from GraphQL (#101). Not ready.",
     {"taskflow/api/graphql_schema.py": ("set", '"""Experimental GraphQL schema (not wired up)."""\n\nSCHEMA = """\ntype Task { id: ID!, title: String!, done: Boolean! }\ntype Query { tasks(page: Int): [Task!]! }\n"""\n')}),
    ("checkout", "main"),
]

# ------------------------------------------------------------------ filler work between key commits
# Real repositories are mostly small commits. These are generated with a fixed seed, so every
# machine produces the same history. (period start, end, active authors, count)
ERAS = [
    ("2025-03-11", "2025-08-31", ["ada", "sara", "leo", "mina", "omar"], 40),
    ("2025-09-01", "2025-12-31", ["ada", "sara", "leo", "mina", "omar", "jonas", "priya"], 45),
    ("2026-01-01", "2026-09-28", ["ada", "sara", "mina", "omar", "jonas", "priya", "lucia"], 60),
]
LEFT = {"leo": "2025-09-10", "sara": "2026-02-10"}          # contributors who moved on
CONVENTIONAL = {"jonas", "priya"}                             # people who write "fix: ..." style messages

FILLER = [
    # (kind, subject, file, text to append)
    ("docs", "Clarify installation steps in the README", "docs/install.md", "Run `pip install -e .` from a virtual environment."),
    ("docs", "Document the search syntax", "docs/usage.md", "Search matches words in task titles."),
    ("docs", "Add a FAQ entry about time zones", "docs/faq.md", "Due dates use your computer's local time zone."),
    ("docs", "Fix broken link in the contributing guide", "docs/contributing.md", "See the issue tracker for good first issues."),
    ("docs", "Explain recurring task rules", "docs/usage.md", "Monthly tasks on the 29th-31st move to the 28th."),
    ("docs", "Update screenshots in the README", "docs/usage.md", "Screenshots show the colored CLI."),
    ("test", "Add tests for tag parsing", "tests/test_tags.py", "def test_tags_split():\n    assert 'a,b'.split(',') == ['a', 'b']"),
    ("test", "Add regression test for overdue filter", "tests/test_models.py", "def test_due_today_not_overdue():\n    assert True"),
    ("test", "Test recurring monthly edge cases", "tests/test_recurring.py", "def test_monthly_31st():\n    assert True"),
    ("test", "Cover API authentication errors", "tests/test_api.py", "def test_missing_token_is_401():\n    assert True"),
    ("test", "Speed up the test suite with an in-memory database", "tests/conftest.py", "DB = ':memory:'"),
    ("test", "Add property-based tests for pagination", "tests/test_pagination.py", "def test_pages_cover_everything():\n    assert True"),
    ("fix", "Handle empty task titles", "taskflow/validation.py", "def valid_title(t):\n    return bool(t.strip())"),
    ("fix", "Fix typo in the help text", "docs/cli-help.txt", "Usage: taskflow add TITLE [--due DATE]"),
    ("fix", "Show a clear error when the database is locked", "taskflow/errors.py", "LOCKED = 'The task database is busy; try again.'"),
    ("fix", "Trim whitespace around tags", "taskflow/validation.py", "def clean_tag(t):\n    return t.strip().lower()"),
    ("fix", "Fix crash when a due date is malformed", "taskflow/validation.py", "def parse_due(s):\n    from datetime import date\n    try:\n        return date.fromisoformat(s)\n    except ValueError:\n        return None"),
    ("fix", "Return 404 instead of 500 for unknown tasks", "taskflow/errors.py", "NOT_FOUND = 'Task not found.'"),
    ("chore", "Bump pytest to 8.3", "requirements-dev.txt", "pytest==8.3.2"),
    ("chore", "Update .gitignore for editor files", ".gitignore", ".vscode/"),
    ("chore", "Pin the Python version for local development", ".python-version", "3.12"),
    ("chore", "Update dependencies", "requirements-dev.txt", "coverage==7.6.1"),
    ("refactor", "Extract date parsing into a helper", "taskflow/dates.py", "def parse(s):\n    from datetime import date\n    return date.fromisoformat(s)"),
    ("refactor", "Rename variables in the storage module for clarity", "docs/internals.md", "Storage uses 'row' for database rows and 'task' for models."),
    ("refactor", "Simplify error handling in the CLI", "taskflow/errors.py", "def friendly(e):\n    return str(e)"),
    ("style", "Format code with black", "pyproject.toml", "[tool.black]\nline-length = 100"),
    ("style", "Sort imports", "pyproject.toml", "[tool.isort]\nprofile = 'black'"),
    ("perf", "Avoid reloading config on every command", "taskflow/settings.py", "_CACHE = {}"),
    ("perf", "Batch inserts when importing tasks", "docs/internals.md", "Imports insert 500 rows per transaction."),
]
CONVENTIONAL_PREFIX = {"docs": "docs", "test": "test", "fix": "fix", "chore": "chore", "refactor": "refactor",
                       "style": "style", "perf": "perf"}


def filler_steps(seed: int = 7) -> list[tuple]:
    """Deterministic small commits: (author, date, message, path, line) tuples grouped by era."""
    rng = random.Random(seed)
    out = []
    for start, end, authors, count in ERAS:
        from datetime import date, timedelta
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
        days = (d1 - d0).days
        picks = sorted(rng.randrange(days) for _ in range(count))
        for n, offset in enumerate(picks):
            day = d0 + timedelta(days=offset)
            candidates = [a for a in authors if a not in LEFT or str(day) < LEFT[a]]
            author = rng.choice(candidates)
            kind, subject, path, text = rng.choice(FILLER)
            message = f"{CONVENTIONAL_PREFIX[kind]}: {subject[0].lower()}{subject[1:]}" if author in CONVENTIONAL else subject
            hour, minute = rng.randrange(8, 19), rng.randrange(60)
            tz = "+01:00" if day.month in (1, 2, 3, 11, 12) else "+02:00"
            out.append((author, f"{day}T{hour:02d}:{minute:02d}:00{tz}", message, path, f"{text}\n"))
    return out
