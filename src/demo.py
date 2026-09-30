"""The built-in demo project: a small, generated Git repository with a meaningful history.

"TaskFlow" is a toy task tracker whose history covers what GitLore is good at: changes with a clear
*why* in the message (sessions -> JWT, JSON -> SQLite, SHA-256 -> PBKDF2), a bug fix, a feature
branch with a merge, a revert and a rename. Authors, dates and contents are fixed, so the commit
hashes are identical on every machine.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import git

from src import config

NAME = "TaskFlow (demo)"
AUTHORS = {
    "ada": ("Ada Park", "ada@taskflow.example"),
    "leo": ("Leo Martin", "leo@taskflow.example"),
    "sara": ("Sara Yilmaz", "sara@taskflow.example"),
}

README_V1 = """# TaskFlow

A tiny command-line task tracker.

    python -m taskflow add "Write the report" --due 2025-02-01
    python -m taskflow list
"""

TASKS_V1 = '''"""Task model and basic operations."""

from dataclasses import dataclass


@dataclass
class Task:
    id: int
    title: str
    done: bool = False


def add_task(tasks: list[Task], title: str) -> Task:
    task = Task(id=len(tasks) + 1, title=title)
    tasks.append(task)
    return task


def list_tasks(tasks: list[Task]) -> list[Task]:
    return [t for t in tasks if not t.done]
'''

TASKS_DUE = '''"""Task model and basic operations."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    due: date | None = None


def add_task(tasks: list[Task], title: str, due: date | None = None) -> Task:
    task = Task(id=len(tasks) + 1, title=title, due=due)
    tasks.append(task)
    return task


def list_tasks(tasks: list[Task]) -> list[Task]:
    return [t for t in tasks if not t.done]


def overdue(tasks: list[Task], today: date) -> list[Task]:
    """Open tasks whose due date has passed."""
    return [t for t in tasks if not t.done and t.due is not None and t.due <= today]
'''

TASKS_DUE_FIXED = TASKS_DUE.replace("t.due <= today]", "t.due < today]")

TASKS_PRIORITY = TASKS_DUE_FIXED.replace(
    "    due: date | None = None\n",
    "    due: date | None = None\n    priority: int = 2  # 1 = high, 2 = normal, 3 = low\n",
).replace(
    "def add_task(tasks: list[Task], title: str, due: date | None = None) -> Task:\n"
    "    task = Task(id=len(tasks) + 1, title=title, due=due)",
    "def add_task(tasks: list[Task], title: str, due: date | None = None, priority: int = 2) -> Task:\n"
    "    task = Task(id=len(tasks) + 1, title=title, due=due, priority=priority)",
)

TASKS_SORTED = TASKS_PRIORITY.replace(
    "def list_tasks(tasks: list[Task]) -> list[Task]:\n    return [t for t in tasks if not t.done]\n",
    "def list_tasks(tasks: list[Task]) -> list[Task]:\n"
    "    \"\"\"Open tasks, most important first; tasks without a due date go last.\"\"\"\n"
    "    open_tasks = [t for t in tasks if not t.done]\n"
    "    return sorted(open_tasks, key=lambda t: (t.priority, t.due or date.max))\n",
)

STORAGE_JSON = '''"""Save and load tasks as JSON."""

import json
from dataclasses import asdict
from pathlib import Path

from taskflow.tasks import Task

DB_FILE = Path.home() / ".taskflow.json"


def save(tasks: list[Task]) -> None:
    DB_FILE.write_text(json.dumps([asdict(t) for t in tasks], default=str))


def load() -> list[Task]:
    if not DB_FILE.exists():
        return []
    return [Task(**row) for row in json.loads(DB_FILE.read_text())]
'''

STORAGE_SQLITE = '''"""Save and load tasks in SQLite.

SQLite handles concurrent writers safely; the old JSON file could be corrupted when two
commands wrote at the same time.
"""

import sqlite3
from pathlib import Path

from taskflow.tasks import Task

DB_FILE = Path.home() / ".taskflow.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT, done INTEGER, "
        "due TEXT, priority INTEGER)"
    )
    return conn


def save(tasks: list[Task]) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM tasks")
        conn.executemany(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?)",
            [(t.id, t.title, int(t.done), t.due and t.due.isoformat(), t.priority) for t in tasks],
        )


def load() -> list[Task]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, title, done, due, priority FROM tasks").fetchall()
    return [Task(id=r[0], title=r[1], done=bool(r[2]), due=r[3], priority=r[4]) for r in rows]
'''

AUTH_SESSIONS = '''"""User login with server-side sessions."""

import hashlib
import secrets

USERS: dict[str, str] = {}      # username -> password hash
SESSIONS: dict[str, str] = {}   # session id -> username


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def register(username: str, password: str) -> None:
    USERS[username] = _hash(password)


def login(username: str, password: str) -> str | None:
    if USERS.get(username) != _hash(password):
        return None
    session_id = secrets.token_hex(16)
    SESSIONS[session_id] = username
    return session_id


def current_user(session_id: str) -> str | None:
    return SESSIONS.get(session_id)
'''

AUTH_JWT = '''"""User login with signed JWT tokens (stateless)."""

import base64
import hashlib
import hmac
import json
import os

USERS: dict[str, str] = {}   # username -> password hash
SECRET = os.environ.get("TASKFLOW_SECRET", "dev-secret").encode()


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def register(username: str, password: str) -> None:
    USERS[username] = _hash(password)


def login(username: str, password: str) -> str | None:
    if USERS.get(username) != _hash(password):
        return None
    payload = _b64(json.dumps({"sub": username}).encode())
    signature = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def current_user(token: str) -> str | None:
    payload, _, signature = token.partition(".")
    expected = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))["sub"]
'''

AUTH_PBKDF2 = AUTH_JWT.replace(
    'def _hash(password: str) -> str:\n    return hashlib.sha256(password.encode()).hexdigest()\n',
    'def _hash(password: str, salt: bytes | None = None) -> str:\n'
    '    """PBKDF2 with a per-user salt: slow on purpose, so stolen hashes are hard to crack."""\n'
    '    salt = salt or os.urandom(16)\n'
    '    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)\n'
    '    return salt.hex() + ":" + digest.hex()\n\n\n'
    'def _verify(password: str, stored: str) -> bool:\n'
    '    salt, _, _ = stored.partition(":")\n'
    '    return hmac.compare_digest(_hash(password, bytes.fromhex(salt)), stored)\n',
).replace(
    "    if USERS.get(username) != _hash(password):\n        return None\n    payload",
    "    stored = USERS.get(username)\n    if stored is None or not _verify(password, stored):\n        return None\n    payload",
)

AUTH_EXPIRY = AUTH_PBKDF2.replace(
    "import os\n",
    "import os\nimport time\n",
).replace(
    'SECRET = os.environ.get("TASKFLOW_SECRET", "dev-secret").encode()\n',
    'SECRET = os.environ.get("TASKFLOW_SECRET", "dev-secret").encode()\n'
    'TOKEN_LIFETIME = 60 * 60 * 8   # 8 hours: long enough for a work day, short enough if a token leaks\n',
).replace(
    'json.dumps({"sub": username})',
    'json.dumps({"sub": username, "exp": int(time.time()) + TOKEN_LIFETIME})',
).replace(
    '    return json.loads(base64.urlsafe_b64decode(padded))["sub"]\n',
    '    claims = json.loads(base64.urlsafe_b64decode(padded))\n'
    '    if claims.get("exp", 0) < time.time():\n'
    '        return None  # expired: the user has to log in again\n'
    '    return claims["sub"]\n\n\n'
    'def refresh(token: str) -> str | None:\n'
    '    """Issue a fresh token for a still-valid one, so active users are not logged out mid-task."""\n'
    '    user = current_user(token)\n'
    '    if user is None:\n'
    '        return None\n'
    '    payload = _b64(json.dumps({"sub": user, "exp": int(time.time()) + TOKEN_LIFETIME}).encode())\n'
    '    signature = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())\n'
    '    return f"{payload}.{signature}"\n',
)

EXPORT_CSV = '''"""Export tasks to CSV."""

import csv
from pathlib import Path

from taskflow.tasks import Task


def export_csv(tasks: list[Task], path: Path) -> None:
    with open(path, "w") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "title", "done", "due", "priority"])
        for t in tasks:
            writer.writerow([t.id, t.title, t.done, t.due, t.priority])
'''

# Each step: (author, ISO date, message, {path: content | None to delete}); special steps are tuples
# starting with "branch", "checkout", "merge", "revert" or "rename".
STEPS: list[tuple] = [
    ("ada", "2025-01-06T10:15:00+01:00", "Initial project structure",
     {"README.md": README_V1, "taskflow/__init__.py": "", "taskflow/tasks.py": TASKS_V1,
      "requirements.txt": "# no third-party dependencies yet\n"}),
    ("ada", "2025-01-08T14:02:00+01:00",
     "Add JSON storage for tasks\n\nTasks only lived in memory and were lost every time the program exited.\n"
     "Save them to ~/.taskflow.json after each change and load them on start.",
     {"taskflow/storage.py": STORAGE_JSON}),
    ("leo", "2025-01-13T09:40:00+01:00",
     "Add user login with server-side sessions\n\nNeeded so several people can share one TaskFlow server.\n"
     "Sessions are kept in memory on the server for now.",
     {"taskflow/auth.py": AUTH_SESSIONS}),
    ("sara", "2025-01-20T16:25:00+01:00",
     "Add due dates and an overdue filter\n\nRequested in issue #7: people want to see what they are late on.",
     {"taskflow/tasks.py": TASKS_DUE}),
    ("leo", "2025-02-03T11:05:00+01:00",
     "Switch login from server sessions to JWT tokens\n\n"
     "Server-side sessions broke when we started running two app instances behind the load\n"
     "balancer: a user who logged in on one instance was logged out on the other, because each\n"
     "instance only knew its own sessions. Signed JWT tokens are stateless, so any instance can\n"
     "verify them without shared storage.",
     {"taskflow/auth.py": AUTH_JWT}),
    ("ada", "2025-02-05T08:50:00+01:00",
     "Fix overdue filter including tasks due today\n\nA task due today is not overdue yet; the filter used <= instead of <.\n"
     "Reported in issue #12.",
     {"taskflow/tasks.py": TASKS_DUE_FIXED}),
    ("branch", "priorities"),
    ("sara", "2025-02-10T13:30:00+01:00",
     "Add task priorities\n\nHigh, normal and low (1-3). Defaults to normal so existing tasks keep working.",
     {"taskflow/tasks.py": TASKS_PRIORITY}),
    ("sara", "2025-02-11T10:10:00+01:00",
     "Sort task list by priority, then due date\n\nTasks without a due date go last.",
     {"taskflow/tasks.py": TASKS_SORTED}),
    ("checkout", "main"),
    ("leo", "2025-02-12T15:45:00+01:00",
     "Hash passwords with PBKDF2 instead of plain SHA-256\n\n"
     "Security review finding: a single unsalted SHA-256 is fast to brute-force if the user table\n"
     "leaks. PBKDF2 with a random per-user salt and 600,000 iterations follows the current OWASP\n"
     "recommendation.",
     {"taskflow/auth.py": AUTH_PBKDF2}),
    ("merge", "ada", "2025-02-14T09:00:00+01:00", "priorities",
     "Merge branch 'priorities'\n\nAdds task priorities and sorts the task list by them."),
    ("ada", "2025-02-20T17:20:00+01:00",
     "Move storage from JSON to SQLite\n\nThe JSON file got corrupted when two commands wrote at the same time\n"
     "(issue #15). SQLite handles concurrent writers safely and ships with Python.",
     {"taskflow/storage.py": STORAGE_SQLITE}),
    ("sara", "2025-02-24T11:00:00+01:00", "Add CSV export", {"taskflow/export.py": EXPORT_CSV}),
    ("revert", "sara", "2025-02-26T09:15:00+01:00",
     'Revert "Add CSV export"\n\nThe export writes blank lines between rows on Windows because the file is\n'
     "not opened with newline=''. Reverting until it is fixed and tested on all platforms."),
    ("rename", "leo", "2025-03-03T14:00:00+01:00", "taskflow/tasks.py", "taskflow/models.py",
     "Rename tasks.py to models.py\n\nThe module holds the data model; 'tasks' was confusing next to the CLI's 'tasks' command.\n"
     "Imports updated."),
    ("ada", "2025-03-05T16:40:00+01:00",
     "Add token expiry and refresh\n\nTokens never expired, so a leaked token worked forever. They now last 8 hours,\n"
     "and refresh() lets active users get a new one without logging in again.",
     {"taskflow/auth.py": AUTH_EXPIRY}),
    ("ada", "2025-03-10T10:00:00+01:00", "Release 1.0",
     {"README.md": README_V1 + "\n## Changelog\n\n### 1.0 (2025-03-10)\n\n- Tasks with due dates and priorities\n"
      "- Login with expiring JWT tokens and PBKDF2 password hashing\n- SQLite storage\n"}),
]


def repo_path() -> Path:
    return config.DEMO_DIR / "taskflow"


def ensure_demo() -> Path:
    """Create the demo repository if it doesn't exist yet; return its path."""
    path = repo_path()
    try:
        if git.Repo(path).head.is_valid():
            return path
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        pass
    if path.exists():
        shutil.rmtree(path)  # an interrupted earlier attempt
    _build(path)
    return path


def _env(author: str, date: str) -> dict[str, str]:
    name, email = AUTHORS[author]
    return {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": date}


def _build(path: Path) -> None:
    path.mkdir(parents=True)
    repo = git.Repo.init(path, initial_branch="main")
    with repo.config_writer() as cw:  # identical bytes on every OS -> identical hashes
        cw.set_value("core", "autocrlf", "false")
        cw.set_value("commit", "gpgsign", "false")
        cw.set_value("user", "name", "GitLore Demo")
        cw.set_value("user", "email", "demo@gitlore.example")
    g = repo.git
    for step in STEPS:
        kind = step[0]
        if kind == "branch":
            g.checkout("-b", step[1])
        elif kind == "checkout":
            g.checkout(step[1])
        elif kind == "merge":
            _, author, date, branch, message = step
            with g.custom_environment(**_env(author, date)):
                g.merge("--no-ff", branch, "-m", message)
        elif kind == "revert":
            _, author, date, message = step
            with g.custom_environment(**_env(author, date)):
                g.revert("--no-edit", "HEAD")
                g.commit("--amend", "-m", message)
        elif kind == "rename":
            _, author, date, old, new, message = step
            g.mv(old, new)
            for py in (path / "taskflow").glob("*.py"):
                text = py.read_text(encoding="utf-8")
                if "taskflow.tasks" in text:
                    py.write_text(text.replace("taskflow.tasks", "taskflow.models"), encoding="utf-8", newline="\n")
            g.add("-A")
            with g.custom_environment(**_env(author, date)):
                g.commit("-m", message)
        else:
            author, date, message, files = step
            for rel, content in files.items():
                target = path / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            g.add("-A")
            with g.custom_environment(**_env(author, date)):
                g.commit("-m", message)
