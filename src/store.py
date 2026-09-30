"""Projects, chats, messages and settings, stored in SQLite (data/gitlore.db).

A *project* is one local Git repository plus its chats. Deleting a project only forgets it here;
the repository on disk is never touched.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from src import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    path           TEXT NOT NULL UNIQUE,
    is_demo        INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    last_opened_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chats (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    activity   INTEGER NOT NULL DEFAULT 0     -- increases on every change; orders the chat list
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY,
    chat_id    INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    commits    TEXT NOT NULL DEFAULT '[]',   -- JSON list of commits the answer used
    focus      TEXT,                         -- JSON: selection/file/commit the question was about
    seconds    REAL,                         -- time until the first word, for assistant messages
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


# Timestamps have one-second resolution, so ordering uses this ever-increasing counter instead.
_NEXT_ACTIVITY = "(SELECT COALESCE(MAX(activity), 0) + 1 FROM chats)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


# --------------------------------------------------------------------------- settings
def get_setting(key: str, default: str | None = None) -> str | None:
    with _db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _db() as db:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


# --------------------------------------------------------------------------- projects
def list_projects() -> list[dict]:
    with _db() as db:
        rows = db.execute("SELECT * FROM projects ORDER BY is_demo DESC, last_opened_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> dict | None:
    with _db() as db:
        return _row(db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


def find_project_by_path(path: str) -> dict | None:
    with _db() as db:
        return _row(db.execute("SELECT * FROM projects WHERE path = ?", (path,)).fetchone())


def add_project(name: str, path: str, is_demo: bool = False) -> dict:
    """Add a project, or return the existing one for the same path."""
    existing = find_project_by_path(path)
    if existing:
        return existing
    now = _now()
    with _db() as db:
        cur = db.execute(
            "INSERT INTO projects (name, path, is_demo, created_at, last_opened_at) VALUES (?, ?, ?, ?, ?)",
            (name, path, int(is_demo), now, now),
        )
        project_id = cur.lastrowid
    return get_project(project_id)


def rename_project(project_id: int, name: str) -> dict | None:
    with _db() as db:
        db.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))
    return get_project(project_id)


def touch_project(project_id: int) -> None:
    with _db() as db:
        db.execute("UPDATE projects SET last_opened_at = ? WHERE id = ?", (_now(), project_id))


def delete_project(project_id: int) -> None:
    with _db() as db:
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))


# --------------------------------------------------------------------------- chats
def list_chats(project_id: int) -> list[dict]:
    with _db() as db:
        rows = db.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS message_count "
            "FROM chats c WHERE project_id = ? ORDER BY activity DESC, id DESC",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_chat(chat_id: int) -> dict | None:
    with _db() as db:
        return _row(db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone())


def create_chat(project_id: int, title: str) -> dict:
    now = _now()
    with _db() as db:
        cur = db.execute("INSERT INTO chats (project_id, title, created_at, updated_at, activity) "
                         f"VALUES (?, ?, ?, ?, {_NEXT_ACTIVITY})", (project_id, title, now, now))
        chat_id = cur.lastrowid
    return get_chat(chat_id)


def rename_chat(chat_id: int, title: str) -> dict | None:
    with _db() as db:
        db.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
    return get_chat(chat_id)


def delete_chat(chat_id: int) -> None:
    with _db() as db:
        db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


# --------------------------------------------------------------------------- messages
def _message(row: sqlite3.Row) -> dict:
    m = dict(row)
    m["commits"] = json.loads(m["commits"] or "[]")
    m["focus"] = json.loads(m["focus"]) if m["focus"] else None
    return m


def list_messages(chat_id: int) -> list[dict]:
    with _db() as db:
        rows = db.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()
    return [_message(r) for r in rows]


def add_message(chat_id: int, role: str, content: str, commits: list[dict] | None = None,
                focus: dict | None = None, seconds: float | None = None) -> int:
    now = _now()
    with _db() as db:
        cur = db.execute(
            "INSERT INTO messages (chat_id, role, content, commits, focus, seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, role, content, json.dumps(commits or []), json.dumps(focus) if focus else None, seconds, now),
        )
        db.execute(f"UPDATE chats SET updated_at = ?, activity = {_NEXT_ACTIVITY} WHERE id = ?", (now, chat_id))
        return cur.lastrowid


def update_message(message_id: int, **fields: Any) -> None:
    """Update content/commits/seconds of a message (used while an answer streams in)."""
    allowed = {"content", "commits", "seconds"}
    sets, values = [], []
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"cannot update {key}")
        sets.append(f"{key} = ?")
        values.append(json.dumps(value) if key == "commits" else value)
    if not sets:
        return
    with _db() as db:
        db.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", (*values, message_id))
