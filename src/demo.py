"""The built-in demo project: a small, generated Git repository with a meaningful history.

"TaskFlow" is a toy task tracker whose history covers what GitLore is good at: changes with a clear
*why* in the message (sessions -> JWT, JSON -> SQLite, SHA-256 -> PBKDF2), a bug fix, a feature
branch with a merge, a revert and a rename. Authors, dates and contents are fixed, so the commit
hashes are identical on every machine.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from datetime import datetime
from pathlib import Path

import git

from src import config, demo_story

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


DEMO_VERSION = "2"  # bump when the story changes; an older demo repository is rebuilt


def repo_path() -> Path:
    # One folder per demo version: upgrading never has to delete a folder another program may have open.
    return config.DEMO_DIR / f"taskflow-{DEMO_VERSION}"


def _marker(path: Path) -> Path:
    return path / ".git" / "gitlore-demo-version"


def is_current() -> bool:
    marker = _marker(repo_path())
    return marker.is_file() and marker.read_text().strip() == DEMO_VERSION


def ensure_demo() -> Path:
    """Create (or upgrade) the demo repository; return its path."""
    path = repo_path()
    try:
        if git.Repo(path).head.is_valid() and is_current():
            return path
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        pass
    if path.exists():
        shutil.rmtree(path, onerror=_force_remove)  # an interrupted earlier build of this version
    _build(path)
    for old in config.DEMO_DIR.iterdir():         # older demo versions: removed when possible
        if old.is_dir() and old != path and old.name.startswith("taskflow"):
            shutil.rmtree(old, ignore_errors=True)
    return path


def _force_remove(func, target, _exc):
    os.chmod(target, stat.S_IWRITE)  # git marks object files read-only on Windows
    func(target)


# ---------------------------------------------------------------------------------------------- builder
class _History:
    """Builds the whole history in memory, then writes it with one `git fast-import` stream.

    One process instead of three git calls per commit: ~200 commits take well under a second, and the
    result is byte-for-byte identical on every machine (same hashes everywhere).
    """

    def __init__(self) -> None:
        self.authors = {**AUTHORS, **demo_story.AUTHORS_LATER}
        self.files: dict[str, dict[str, str]] = {"main": {}}
        self.heads: dict[str, int | None] = {"main": None}
        self.fork_base: dict[str, dict[str, str]] = {}
        self.branch = "main"
        self.mark = 0
        self.out: list[bytes] = []
        self.last_key_change: dict[str, dict[str, str | None]] = {}  # branch -> {path: content before}

    @staticmethod
    def _stamp(iso: str) -> str:
        dt = datetime.fromisoformat(iso)
        minutes = int(dt.utcoffset().total_seconds() // 60)
        sign = "+" if minutes >= 0 else "-"
        return f"{int(dt.timestamp())} {sign}{abs(minutes) // 60:02d}{abs(minutes) % 60:02d}"

    def _data(self, text: str) -> None:
        raw = text.encode("utf-8")
        self.out.append(b"data %d\n" % len(raw) + raw + b"\n")

    def _person(self, author: str, date: str) -> str:
        name, email = self.authors[author]
        return f"{name} <{email}> {self._stamp(date)}"

    def commit(self, author: str, date: str, message: str, new_files: dict[str, str],
               merge_from: str | None = None, key: bool = True) -> None:
        before = self.files[self.branch]
        self.mark += 1
        who = self._person(author, date)
        self.out.append(f"commit refs/heads/{self.branch}\nmark :{self.mark}\nauthor {who}\ncommitter {who}\n".encode())
        self._data(message.rstrip("\n") + "\n")
        if self.heads[self.branch] is not None:
            self.out.append(f"from :{self.heads[self.branch]}\n".encode())
        if merge_from:
            self.out.append(f"merge :{self.heads[merge_from]}\n".encode())
        for path in sorted(set(before) | set(new_files)):
            if path not in new_files:
                self.out.append(f"D {path}\n".encode())
            elif before.get(path) != new_files[path]:
                self.out.append(f"M 100644 inline {path}\n".encode())
                self._data(new_files[path])
        self.out.append(b"\n")
        if key:
            self.last_key_change[self.branch] = {p: before.get(p) for p in set(before) | set(new_files)
                                                 if before.get(p) != new_files.get(p)}
        self.files[self.branch] = dict(new_files)
        self.heads[self.branch] = self.mark

    def tag(self, name: str, author: str, date: str, message: str) -> None:
        self.out.append(f"tag {name}\nfrom :{self.heads[self.branch]}\ntagger {self._person(author, date)}\n".encode())
        self._data(message.rstrip("\n") + "\n")

    def start_branch(self, name: str) -> None:
        self.files[name] = dict(self.files[self.branch])
        self.heads[name] = self.heads[self.branch]
        self.fork_base[name] = dict(self.files[self.branch])
        self.branch = name

    def merged(self, other: str) -> dict[str, str]:
        base, theirs, ours = self.fork_base[other], self.files[other], dict(self.files[self.branch])
        for path in set(base) | set(theirs):
            if base.get(path) != theirs.get(path):
                if path in theirs:
                    ours[path] = theirs[path]
                else:
                    ours.pop(path, None)
        return ours

    def reverted(self) -> dict[str, str]:
        files = dict(self.files[self.branch])
        for path, old in self.last_key_change[self.branch].items():
            if old is None:
                files.pop(path, None)
            else:
                files[path] = old
        return files


def _apply_edits(files: dict[str, str], edits: dict) -> dict[str, str]:
    files = dict(files)
    for path, ops in edits.items():
        for op in ops if isinstance(ops, list) else [ops]:
            kind = op[0]
            if kind == "set":
                files[path] = op[1]
            elif kind == "append":
                files[path] = files.get(path, "") + op[1]
            elif kind == "replace":
                if op[1] not in files[path]:
                    raise ValueError(f"demo story: {path} doesn't contain {op[1][:50]!r}")
                files[path] = files[path].replace(op[1], op[2])
            elif kind == "delete":
                files.pop(path, None)
    return files


def _step_date(step: tuple) -> str:
    return step[3] if step[0] == "tag" else step[2]


def _run(h: _History, step: tuple) -> None:
    kind = step[0]
    if kind == "branch":
        h.start_branch(step[1])
    elif kind == "checkout":
        h.branch = step[1]
    elif kind == "merge":
        _, author, date, branch, message = step
        h.commit(author, date, message, h.merged(branch), merge_from=branch)
    elif kind == "revert":
        _, author, date, message = step
        h.commit(author, date, message, h.reverted())
    elif kind == "rename":  # era 1
        _, author, date, old, new, message = step
        files = dict(h.files[h.branch])
        files[new] = files.pop(old)
        files = {p: c.replace("taskflow.tasks", "taskflow.models") for p, c in files.items()}
        h.commit(author, date, message, files)
    elif kind == "edit":
        _, author, date, message, edits = step
        h.commit(author, date, message, _apply_edits(h.files[h.branch], edits))
    elif kind == "tag":
        _, name, author, date, message = step
        h.tag(name, author, date, message)
    elif kind == "restructure":
        _, author, date, message, moves, imports = step
        files = dict(h.files[h.branch])
        for old, new in moves.items():
            files[new] = files.pop(old)
        for pkg in ("taskflow/core/__init__.py", "taskflow/api/__init__.py", "taskflow/cli/__init__.py"):
            files[pkg] = ""
        for old, new in sorted(imports.items(), key=lambda kv: -len(kv[0])):
            files = {p: c.replace(old, new) for p, c in files.items()}
        h.commit(author, date, message, files)
    elif kind == "filler":
        _, author, date, message, path, line = step
        files = dict(h.files["main"])
        files[path] = files.get(path, "") + line
        h.commit(author, date, message, files, key=False)
    else:  # era 1 plain commit: (author, date, message, {path: content | None})
        author, date, message, changes = step
        files = dict(h.files[h.branch])
        for rel, content in changes.items():
            if content is None:
                files.pop(rel, None)
            else:
                files[rel] = content
        h.commit(author, date, message, files)


def _later_blocks() -> list[list[tuple]]:
    """Key steps grouped so a branch's commits stay together, then merged by date with filler work."""
    blocks, current = [], []
    for step in demo_story.KEY_STEPS:
        current.append(step)
        in_branch = any(s[0] == "branch" for s in current) and not any(s[0] == "checkout" for s in current)
        if step[0] == "branch" or in_branch:
            continue
        blocks.append(current)
        current = []
    dated = [(_step_date(next(s for s in b if s[0] not in ("branch", "checkout"))), b) for b in blocks]
    dated += [(f[1], [("filler", *f)]) for f in demo_story.filler_steps()]
    return [b for _, b in sorted(dated, key=lambda x: x[0][:16])]


def _build(path: Path) -> None:
    h = _History()
    for step in STEPS:
        _run(h, step)
    h.tag("v1.0.0", "ada", "2025-03-10T10:05:00+01:00",
          "TaskFlow 1.0\n\n- Tasks with due dates and priorities\n- Login with expiring JWT tokens\n- SQLite storage")
    for block in _later_blocks():
        for step in block:
            _run(h, step)
    path.mkdir(parents=True)
    repo = git.Repo.init(path, initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("core", "autocrlf", "false")
        cw.set_value("commit", "gpgsign", "false")
        cw.set_value("user", "name", "GitLore Demo")
        cw.set_value("user", "email", "demo@gitlore.example")
    subprocess.run(["git", "fast-import", "--quiet", "--done"], cwd=path,
                   input=b"".join(h.out) + b"done\n", check=True, capture_output=True)
    repo.git.reset("--hard", "main")
    _marker(path).write_text(DEMO_VERSION)
