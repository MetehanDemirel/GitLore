from __future__ import annotations

from pathlib import Path

import pytest

from src import config, store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gitlore.db")


def test_settings_round_trip():
    assert store.get_setting("theme", "system") == "system"
    store.set_setting("theme", "dark")
    store.set_setting("theme", "light")
    assert store.get_setting("theme") == "light"


def test_projects_add_is_idempotent_and_demo_first():
    a = store.add_project("app", "/repos/app")
    assert store.add_project("other name", "/repos/app")["id"] == a["id"]
    demo = store.add_project("TaskFlow (demo)", "/data/demo", is_demo=True)
    assert [p["id"] for p in store.list_projects()][0] == demo["id"]
    assert store.rename_project(a["id"], "My App")["name"] == "My App"


def test_deleting_a_project_deletes_its_chats_and_messages():
    p = store.add_project("app", "/repos/app")
    chat = store.create_chat(p["id"], "Why JWT?")
    store.add_message(chat["id"], "user", "Why JWT?")
    store.delete_project(p["id"])
    assert store.get_chat(chat["id"]) is None
    assert store.list_messages(chat["id"]) == []


def test_chats_and_messages():
    p = store.add_project("app", "/repos/app")
    older = store.create_chat(p["id"], "First")
    newer = store.create_chat(p["id"], "Second")
    focus = {"kind": "selection", "path": "auth.py", "commit": "abc1234", "text": "jwt()"}
    store.add_message(older["id"], "user", "What is this?", focus=focus)
    mid = store.add_message(older["id"], "assistant", "")
    store.update_message(mid, content="Because [abc1234].", commits=[{"hash": "abc1234"}], seconds=9.5)

    chats = store.list_chats(p["id"])
    assert [c["id"] for c in chats] == [older["id"], newer["id"]]  # most recently updated first
    assert chats[0]["message_count"] == 2
    messages = store.list_messages(older["id"])
    assert messages[0]["focus"] == focus
    assert messages[1] == {**messages[1], "content": "Because [abc1234].", "commits": [{"hash": "abc1234"}], "seconds": 9.5}

    assert store.rename_chat(newer["id"], "Renamed")["title"] == "Renamed"
    store.delete_chat(newer["id"])
    assert [c["id"] for c in store.list_chats(p["id"])] == [older["id"]]


def test_update_message_rejects_unknown_fields():
    p = store.add_project("app", "/repos/app")
    mid = store.add_message(store.create_chat(p["id"], "c")["id"], "user", "q")
    with pytest.raises(ValueError):
        store.update_message(mid, role="assistant")
