"""API tests: the real app with an isolated data folder and a fake model (GITLORE_FAKE_LLM)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src import config, server, vendor


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    for name, value in [("DATA_DIR", data), ("DB_PATH", data / "gitlore.db"), ("CHROMA_DIR", data / "chroma"),
                        ("DEMO_DIR", data / "demo"), ("VENDOR_DIR", data / "vendor"), ("MODELS_DIR", data / "models")]:
        monkeypatch.setattr(config, name, value)
    monkeypatch.setenv("GITLORE_FAKE_LLM", "1")
    monkeypatch.setattr(vendor, "monaco_ready", lambda: True)  # don't download the editor in tests
    monkeypatch.setattr(server, "JOBS", server.Jobs())
    monkeypatch.setattr(server, "MODELS", server.Models())
    app = server.create_app(extra_hosts=("testserver",))
    with TestClient(app) as c:
        wait_for_jobs()
        yield c


def wait_for_jobs(timeout: float = 120) -> None:
    deadline = time.time() + timeout
    while server.JOBS.running():
        assert time.time() < deadline, "background job did not finish"
        time.sleep(0.1)


def post(c: TestClient, url: str, payload: dict | None = None, method: str = "POST"):
    return c.request(method, url, json=payload or {})


def demo_project(c: TestClient) -> dict:
    return next(p for p in c.get("/api/state").json()["projects"] if p["is_demo"])


def ask(c: TestClient, chat_id: int, question: str, focus: dict | None = None) -> list[dict]:
    with c.stream("POST", f"/api/chats/{chat_id}/ask", json={"question": question, "focus": focus}) as r:
        assert r.status_code == 200
        return [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]


# --------------------------------------------------------------------------- basics & security
def test_first_launch_has_an_indexed_demo_project(client):
    state = client.get("/api/state").json()
    assert state["version"] == config.VERSION
    assert state["settings"]["language"] == "en" and state["settings"]["theme"] == "system"
    [demo] = state["projects"]
    assert demo["is_demo"] and demo["name"] == "TaskFlow (demo)"
    assert demo["indexed"] > 150 and demo["available"]
    assert state["model"]["filename"].endswith(".gguf")


def test_non_json_posts_are_refused(client):
    r = client.post("/api/settings", data={"language": "tr"})  # a form, as another website could send
    assert r.status_code == 415
    assert client.get("/api/state").json()["settings"]["language"] == "en"


def test_foreign_host_header_is_refused(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_settings_are_validated(client):
    post(client, "/api/settings", {"language": "de", "theme": "dark", "commit_count": 500})
    post(client, "/api/settings", {"language": "xx", "theme": "neon", "commit_count": -1})
    s = client.get("/api/state").json()["settings"]
    assert (s["language"], s["theme"], s["commit_count"]) == ("de", "dark", 500)


# --------------------------------------------------------------------------- projects
def test_add_rename_index_and_remove_a_project(client, rb):
    rb.commit("Switch login to JWT", {"auth.py": "jwt = True\n"})
    bad = post(client, "/api/projects", {"path": str(rb.path.parent / "nope")})
    assert bad.status_code == 400 and "Folder not found" in bad.json()["error"]

    r = post(client, "/api/projects", {"path": f'"{rb.path}"'})
    assert r.status_code == 201
    pid = r.json()["id"]
    wait_for_jobs()
    project = next(p for p in client.get("/api/state").json()["projects"] if p["id"] == pid)
    assert project["indexed"] == 1 and project["name"] == "repo"
    assert client.get("/api/state").json()["settings"]["last_project"] == pid

    assert post(client, f"/api/projects/{pid}", {"name": "My Repo"}, "PATCH").json()["name"] == "My Repo"
    assert post(client, f"/api/projects/{pid}", {}, "DELETE").status_code == 200
    assert all(p["id"] != pid for p in client.get("/api/state").json()["projects"])
    assert rb.path.exists(), "removing a project never deletes the repository"


def test_demo_project_cannot_be_removed(client):
    r = post(client, f"/api/projects/{demo_project(client)['id']}", {}, "DELETE")
    assert r.status_code == 400 and "built in" in r.json()["error"]


def test_reindex_job(client):
    pid = demo_project(client)["id"]
    job = post(client, f"/api/projects/{pid}/index", {"rebuild": True}).json()["job"]
    wait_for_jobs()
    status = client.get(f"/api/jobs/{job}").json()
    assert status["status"] == "done" and status["result"]["indexed"] > 150


# --------------------------------------------------------------------------- history & diffs
def test_commit_list_detail_and_diff(client):
    pid = demo_project(client)["id"]
    commits = client.get(f"/api/projects/{pid}/commits").json()
    assert len(commits) > 150
    jwt = next(c for c in commits if c["subject"].startswith("Switch login"))
    assert jwt["hash"] in [c["hash"] for c in client.get(f"/api/projects/{pid}/commits?q=jwt").json()]

    detail = client.get(f"/api/projects/{pid}/commits/{jwt['hash']}").json()
    assert "load\nbalancer" in detail["message"] and [f["path"] for f in detail["files"]] == ["taskflow/auth.py"]
    diff = client.get(f"/api/projects/{pid}/commits/{jwt['hash']}/file", params={"path": "taskflow/auth.py"}).json()
    assert "SESSIONS" in diff["original"] and "hmac" in diff["modified"] and diff["language"] == "python"

    rename = next(c for c in commits if c["subject"].startswith("Rename tasks.py"))
    files = client.get(f"/api/projects/{pid}/commits/{rename['hash']}").json()["files"]
    assert {"path": "taskflow/models.py", "status": "renamed", "old_path": "taskflow/tasks.py"}.items() <= next(
        f for f in files if f["path"] == "taskflow/models.py").items()


def test_bad_commit_is_a_friendly_400(client):
    pid = demo_project(client)["id"]
    r = client.get(f"/api/projects/{pid}/commits/zzzz")
    assert r.status_code == 400 and "commit hash" in r.json()["error"]
    assert client.get("/api/projects/999/commits").status_code == 404


# --------------------------------------------------------------------------- edit & commit
def test_edit_file_and_commit_through_the_api(client):
    pid = demo_project(client)["id"]
    f = client.get(f"/api/projects/{pid}/file", params={"path": "README.md"}).json()
    assert f["current"] == f["head"] and "TaskFlow" in f["current"]
    r = post(client, f"/api/projects/{pid}/file", {"path": "README.md", "content": f["current"] + "\nMore docs.\n"}, "PUT")
    assert r.status_code == 200
    status = client.get(f"/api/projects/{pid}/status").json()
    assert status["branch"] == "main" and [x["path"] for x in status["files"]] == ["README.md"]

    assert post(client, f"/api/projects/{pid}/commit", {"message": "", "paths": ["README.md"]}).status_code == 400
    done = post(client, f"/api/projects/{pid}/commit", {"message": "Document more", "paths": ["README.md"]}).json()
    assert done["subject"] == "Document more"
    assert client.get(f"/api/projects/{pid}/commits").json()[0]["hash"] == done["hash"]
    assert client.get(f"/api/projects/{pid}/status").json()["files"] == []


@pytest.mark.parametrize("path", ["../escape.txt", ".git/config", "C:/Windows/win.ini", "/etc/passwd"])
def test_writing_outside_the_repo_is_refused(client, path):
    pid = demo_project(client)["id"]
    r = post(client, f"/api/projects/{pid}/file", {"path": path, "content": "x"}, "PUT")
    assert r.status_code == 400
    assert "not inside the repository" in r.json()["error"] or "can't be edited" in r.json()["error"]


# --------------------------------------------------------------------------- chats & answers
def test_chat_answer_streams_and_is_saved(client):
    pid = demo_project(client)["id"]
    chat = post(client, f"/api/projects/{pid}/chats").json()
    assert chat["title"] == "New Chat"
    events = ask(client, chat["id"], "Why did login switch to JWT?")
    kinds = [e["type"] for e in events]
    assert kinds[0] == "status" and "commits" in kinds and "token" in kinds and kinds[-1] == "done"
    used = next(e for e in events if e["type"] == "commits")["commits"]
    assert used and used[0]["subject"].startswith("Switch login")
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    assert f"[{used[0]['short_hash']}]" in answer

    msgs = client.get(f"/api/chats/{chat['id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == answer and msgs[1]["commits"] == used and msgs[1]["seconds"] is not None
    chats = client.get(f"/api/projects/{pid}/chats").json()
    assert chats[0]["title"] == "Why did login switch to JWT?", "first question names the chat"


def test_selected_code_puts_its_commit_first(client):
    pid = demo_project(client)["id"]
    commits = client.get(f"/api/projects/{pid}/commits").json()
    target = next(c for c in commits if c["subject"].startswith("Fix overdue"))
    chat = post(client, f"/api/projects/{pid}/chats").json()
    focus = {"path": "taskflow/tasks.py", "commit": target["hash"], "text": "t.due < today"}
    events = ask(client, chat["id"], "Why this comparison?", focus)
    used = next(e for e in events if e["type"] == "commits")["commits"]
    assert used[0]["hash"] == target["hash"]
    assert client.get(f"/api/chats/{chat['id']}/messages").json()[0]["focus"]["text"] == "t.due < today"


def test_missing_model_is_reported_in_the_stream(client, monkeypatch):
    monkeypatch.delenv("GITLORE_FAKE_LLM")
    pid = demo_project(client)["id"]
    chat = post(client, f"/api/projects/{pid}/chats").json()
    events = ask(client, chat["id"], "Anything?")
    assert events[-1]["type"] == "error" and "Download it in Settings" in events[-1]["message"]


def test_rename_and_delete_chat(client):
    pid = demo_project(client)["id"]
    chat = post(client, f"/api/projects/{pid}/chats", {"title": "Old"}).json()
    assert post(client, f"/api/chats/{chat['id']}", {"title": "New title"}, "PATCH").json()["title"] == "New title"
    assert post(client, f"/api/chats/{chat['id']}", {"title": " "}, "PATCH").status_code == 400
    post(client, f"/api/chats/{chat['id']}", method="DELETE")
    assert client.get(f"/api/chats/{chat['id']}/messages").status_code == 404


def test_tagged_commits_are_used_first_and_kept_with_the_question(client):
    pid = demo_project(client)["id"]
    commits = client.get(f"/api/projects/{pid}/commits").json()
    tagged = [commits[5]["hash"], commits[40]["hash"]]
    chat = post(client, f"/api/projects/{pid}/chats", {}).json()
    with client.stream("POST", f"/api/chats/{chat['id']}/ask", json={"question": "Compare these", "tags": tagged}) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    used = next(e for e in events if e["type"] == "commits")["commits"]
    assert [c["hash"] for c in used[:2]] == tagged
    assert client.get(f"/api/chats/{chat['id']}/messages").json()[0]["focus"] == {"tags": tagged}
