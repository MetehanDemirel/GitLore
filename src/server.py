"""GitLore's local web server: a JSON API over src/ plus the static web UI.

Security: listens on 127.0.0.1 only, rejects other Host headers (DNS rebinding) and non-JSON
request bodies (so another website can't post forms to it), because some endpoints write to the
user's repositories.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from src import chat_engine, config, demo, git_ops, model_manager, store, vector_store, vendor
from src.config import ModelPreset
from src.git_ops import GitOpError
from src.git_parser import RepoError, get_commits, open_repo
from src.model_manager import ModelError

DEFAULT_CHAT_TITLE = "New Chat"


# =========================================================================== background jobs
class Jobs:
    """Long-running work (downloads, indexing) on threads, polled by the UI."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, key: str, fn, *args) -> dict:
        """Run fn(progress, *args) in the background; one job per `key` at a time."""
        with self._lock:
            for job in self._jobs.values():
                if job["key"] == key and job["status"] == "running":
                    return job
            job = {"id": uuid.uuid4().hex[:12], "kind": kind, "key": key, "status": "running",
                   "done": 0, "total": 0, "message": None, "result": None}
            self._jobs[job["id"]] = job

        def progress(done: int, total: int, message: str | None = None) -> None:
            job.update(done=done, total=total)
            if message:
                job["message"] = message

        def run() -> None:
            try:
                job["result"] = fn(progress, *args)
                job["status"] = "done"
            except (ModelError, RepoError, GitOpError, vendor.VendorError) as e:
                job.update(status="error", message=str(e))
            except Exception as e:  # never leave a job "running" forever
                job.update(status="error", message=f"Unexpected error: {type(e).__name__}: {e}")

        threading.Thread(target=run, name=f"job-{kind}", daemon=True).start()
        return job

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def running(self) -> list[dict]:
        return [j for j in self._jobs.values() if j["status"] == "running"]


JOBS = Jobs()


# =========================================================================== model access
class Models:
    """One loaded model at a time; generation is serialized (llama.cpp isn't thread-safe)."""

    def __init__(self) -> None:
        self._llm = None
        self._key: tuple[str, str] | None = None
        self.lock = threading.Lock()

    def get(self, preset: ModelPreset):
        key = (preset.repo_id, preset.filename)
        if self._key != key:
            self._llm = None
            self._llm = _fake_llm() if os.environ.get("GITLORE_FAKE_LLM") else model_manager.load_llm(preset)
            self._key = key
        return self._llm

    def unload(self) -> None:
        self._llm, self._key = None, None


MODELS = Models()


def _fake_llm():
    """A stand-in model for UI tests (GITLORE_FAKE_LLM=1): fast, deterministic, cites the first commit."""

    class FakeLlm:
        metadata: dict = {}

        def tokenize(self, data: bytes, add_bos: bool = False, special: bool = False) -> list[int]:
            return list(range((len(data) + 3) // 4))

        def detokenize(self, toks: list[int]) -> bytes:
            return b"x" * (len(toks) * 4)

        def create_chat_completion(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            cited = prompt.split("[", 1)[1][:7] if "[" in prompt else "0000000"
            for word in f"This change is explained in commit [{cited}].".split(" "):
                yield {"choices": [{"delta": {"content": word + " "}}]}

    return FakeLlm()


def current_preset() -> ModelPreset:
    key = store.get_setting("preset", config.DEFAULT_PRESET)
    if key == "custom":
        try:
            return model_manager.custom_preset(store.get_setting("custom_repo", ""), store.get_setting("custom_file", ""))
        except ModelError:
            pass
    return config.MODEL_PRESETS.get(key) or config.MODEL_PRESETS[config.DEFAULT_PRESET]


# =========================================================================== helpers
def ok(data=None, status: int = 200) -> JSONResponse:
    return JSONResponse(data if data is not None else {"ok": True}, status_code=status)


def fail(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def body(request: Request) -> dict:
    """JSON body; anything else is refused so other websites can't submit forms to this server."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "Requests must be JSON.")
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON.") from None
    if not isinstance(data, dict):
        raise HTTPException(400, "Expected a JSON object.")
    return data


def project_or_404(project_id: int) -> dict:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    return project


def chat_or_404(chat_id: int) -> dict:
    chat = store.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found.")
    return chat


def project_view(p: dict) -> dict:
    try:
        indexed = vector_store.count(p["path"])
        available = True
    except RepoError:
        indexed, available = 0, False
    job = next((j for j in JOBS.running() if j["key"] == f"index:{p['id']}"), None)
    return {**p, "is_demo": bool(p["is_demo"]), "indexed": indexed, "available": available,
            "index_job": job and job["id"]}


def _commit_summary(c: dict) -> dict:
    return {"hash": c["hash"], "short_hash": c["short_hash"], "author": c["author"], "date": c["date"],
            "subject": c["message"].splitlines()[0] if c["message"] else "", "files_changed": c["files_changed"]}


# =========================================================================== setup on first launch
def _index_job(progress, project_id: int, max_commits: int, rebuild: bool = False) -> dict:
    project = store.get_project(project_id)
    progress(0, 0, "reading")
    commits = get_commits(project["path"], max_commits)
    if rebuild:
        vector_store.reset(project["path"])
    progress(0, len(commits), "indexing")
    added = vector_store.index_commits(project["path"], commits, on_progress=lambda d, t: progress(d, t, "indexing"))
    return {"added": added, "indexed": vector_store.count(project["path"])}


def ensure_demo_project() -> dict:
    """The built-in demo project is always present; created and indexed on first launch."""
    path = str(demo.ensure_demo())
    project = store.find_project_by_path(path) or store.add_project(demo.NAME, path, is_demo=True)
    if vector_store.count(path) == 0:
        JOBS.start("index", f"index:{project['id']}", _index_job, project["id"], config.DEFAULT_COMMIT_COUNT)
    return project


def ensure_editor() -> None:
    if not vendor.monaco_ready():
        JOBS.start("editor", "editor", lambda progress: str(vendor.ensure_monaco(progress)))


# =========================================================================== lifecycle (auto-shutdown)
class Heartbeat:
    def __init__(self) -> None:
        self.last: float | None = None

    def beat(self) -> None:
        self.last = time.monotonic()

    def watch(self) -> None:
        """Exit once a tab has connected and then no tab has pinged for a while."""
        while True:
            time.sleep(2)
            if self.last is not None and time.monotonic() - self.last > config.IDLE_SHUTDOWN_SECONDS:
                os._exit(0)


HEARTBEAT = Heartbeat()


# =========================================================================== routes: app state
async def health(request: Request) -> Response:
    return ok({"ok": True, "version": config.VERSION})


async def heartbeat(request: Request) -> Response:
    HEARTBEAT.beat()
    return ok()


async def state(request: Request) -> Response:
    preset = current_preset()
    downloaded = model_manager.is_downloaded(preset)
    editor_job = next((j for j in JOBS.running() if j["kind"] == "editor"), None)
    return ok({
        "version": config.VERSION,
        "settings": {
            "language": store.get_setting("language", config.DEFAULT_LANGUAGE),
            "theme": store.get_setting("theme", "system"),
            "preset": store.get_setting("preset", config.DEFAULT_PRESET),
            "custom_repo": store.get_setting("custom_repo", ""),
            "custom_file": store.get_setting("custom_file", ""),
            "commit_count": int(store.get_setting("commit_count", str(config.DEFAULT_COMMIT_COUNT))),
            "last_project": int(store.get_setting("last_project", "0") or 0),
        },
        "languages": config.LANGUAGES,
        "presets": {k: {"label": p.label, "size_gb": p.size_gb} for k, p in config.MODEL_PRESETS.items()},
        "model": {"label": preset.label, "filename": preset.filename, "downloaded": downloaded,
                  "size_gb": round(model_manager.model_path(preset).stat().st_size / 1e9, 2) if downloaded else preset.size_gb},
        "editor": {"ready": vendor.monaco_ready(), "job": editor_job and editor_job["id"],
                   "path": f"/monaco/monaco-{config.MONACO_VERSION}/vs"},
        "projects": [project_view(p) for p in store.list_projects()],
    })


async def update_settings(request: Request) -> Response:
    data = await body(request)
    if "language" in data and data["language"] in config.LANGUAGES:
        store.set_setting("language", data["language"])
    if "theme" in data and data["theme"] in config.THEMES:
        store.set_setting("theme", data["theme"])
    if "preset" in data and (data["preset"] in config.MODEL_PRESETS or data["preset"] == "custom"):
        store.set_setting("preset", data["preset"])
        MODELS.unload()
    for key in ("custom_repo", "custom_file"):
        if key in data and isinstance(data[key], str):
            store.set_setting(key, data[key].strip())
    if "commit_count" in data and isinstance(data["commit_count"], int) and 1 <= data["commit_count"] <= 5000:
        store.set_setting("commit_count", str(data["commit_count"]))
    if "last_project" in data and isinstance(data["last_project"], int):
        store.set_setting("last_project", str(data["last_project"]))
        if store.get_project(data["last_project"]):
            store.touch_project(data["last_project"])
    return ok()


async def job_status(request: Request) -> Response:
    job = JOBS.get(request.path_params["job_id"])
    return ok({k: v for k, v in job.items() if k != "key"}) if job else fail("Job not found.", 404)


# =========================================================================== routes: model & editor
async def download_model(request: Request) -> Response:
    preset = current_preset()
    job = JOBS.start("model", "model", lambda progress: str(model_manager.ensure_model(preset, progress)))
    return ok({"job": job["id"]})


async def delete_model(request: Request) -> Response:
    MODELS.unload()
    try:
        model_manager.delete_model(current_preset())
    except PermissionError:
        return fail("The model file is still in use. Restart GitLore, then remove it again.")
    return ok()


async def download_editor(request: Request) -> Response:
    ensure_editor()
    job = next((j for j in JOBS.running() if j["kind"] == "editor"), None)
    return ok({"job": job and job["id"], "ready": vendor.monaco_ready()})


# =========================================================================== routes: projects
async def add_project(request: Request) -> Response:
    data = await body(request)
    raw = str(data.get("path", "")).strip().strip('"')
    try:
        repo = open_repo(raw)
    except RepoError as e:
        return fail(str(e))
    path = str(Path(repo.working_tree_dir).resolve())
    name = str(data.get("name") or Path(path).name)[:100]
    project = store.add_project(name, path)
    store.set_setting("last_project", str(project["id"]))
    if vector_store.count(path) == 0:
        count = int(store.get_setting("commit_count", str(config.DEFAULT_COMMIT_COUNT)))
        JOBS.start("index", f"index:{project['id']}", _index_job, project["id"], count)
    return ok(project_view(project), 201)


async def update_project(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    data = await body(request)
    name = str(data.get("name", "")).strip()[:100]
    if not name:
        return fail("A project needs a name.")
    return ok(project_view(store.rename_project(project["id"], name)))


async def delete_project(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    if project["is_demo"]:
        return fail("The demo project is built in and can't be removed.")
    try:
        vector_store.reset(project["path"])
    except RepoError:
        pass  # the folder is gone already; just forget it
    store.delete_project(project["id"])
    return ok()


async def index_project(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    data = await body(request)
    count = data.get("max_commits") or int(store.get_setting("commit_count", str(config.DEFAULT_COMMIT_COUNT)))
    job = JOBS.start("index", f"index:{project['id']}", _index_job, project["id"], int(count), bool(data.get("rebuild")))
    return ok({"job": job["id"]})


# =========================================================================== routes: history & files
def _git(fn, *args):
    try:
        return ok(fn(*args))
    except (RepoError, GitOpError) as e:
        return fail(str(e))


async def commits(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    q = request.query_params
    return _git(git_ops.list_commits, project["path"], q.get("q", ""), min(int(q.get("limit", 200)), 1000),
                int(q.get("offset", 0)))


async def commit_detail(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    return _git(git_ops.commit_detail, project["path"], request.path_params["sha"])


async def commit_file(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    q = request.query_params
    return _git(git_ops.file_versions, project["path"], request.path_params["sha"], q.get("path", ""), q.get("old_path"))


async def worktree_status(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    return _git(git_ops.status, project["path"])


async def worktree_tree(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    return _git(git_ops.list_tree, project["path"])


async def worktree_file(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    if request.method == "GET":
        return _git(git_ops.read_file, project["path"], request.query_params.get("path", ""))
    data = await body(request)
    if not isinstance(data.get("content"), str):
        return fail("Missing file content.")
    return _git(lambda: git_ops.write_file(project["path"], str(data.get("path", "")), data["content"]) or {"ok": True})


async def make_commit(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    data = await body(request)
    paths = data.get("paths")
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        return fail("Choose at least one changed file to commit.")
    return _git(git_ops.commit, project["path"], str(data.get("message", "")), paths)


# =========================================================================== routes: chats
async def chats(request: Request) -> Response:
    project = project_or_404(request.path_params["pid"])
    if request.method == "GET":
        return ok(store.list_chats(project["id"]))
    data = await body(request)
    title = str(data.get("title") or DEFAULT_CHAT_TITLE)[:120]
    return ok(store.create_chat(project["id"], title), 201)


async def chat(request: Request) -> Response:
    c = chat_or_404(request.path_params["cid"])
    if request.method == "DELETE":
        store.delete_chat(c["id"])
        return ok()
    data = await body(request)
    title = str(data.get("title", "")).strip()[:120]
    if not title:
        return fail("A chat needs a title.")
    return ok(store.rename_chat(c["id"], title))


async def chat_messages(request: Request) -> Response:
    c = chat_or_404(request.path_params["cid"])
    return ok(store.list_messages(c["id"]))


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _answer_stream(c: dict, project: dict, question: str, focus: dict | None) -> Iterator[str]:
    history_msgs = store.list_messages(c["id"])
    turns = [(q["content"], a["content"]) for q, a in zip(history_msgs[::2], history_msgs[1::2])]
    previous = history_msgs[-1]["commits"] if history_msgs and history_msgs[-1]["role"] == "assistant" else []
    language = store.get_setting("language", config.DEFAULT_LANGUAGE)

    store.add_message(c["id"], "user", question, focus=focus)
    if c["title"] == DEFAULT_CHAT_TITLE:
        store.rename_chat(c["id"], question if len(question) <= 60 else question[:57].rstrip() + "…")
    reply_id = store.add_message(c["id"], "assistant", "")
    started, text, used = time.monotonic(), "", []
    try:
        yield _sse({"type": "status", "stage": "loading"})
        preset = current_preset()
        if not model_manager.is_downloaded(preset) and not os.environ.get("GITLORE_FAKE_LLM"):
            raise ModelError("The model isn't downloaded yet. Download it in Settings first.")
        with MODELS.lock:
            llm = MODELS.get(preset)
            yield _sse({"type": "status", "stage": "searching"})
            follow_up = chat_engine.is_follow_up(question, turns)
            hits = vector_store.search(project["path"], chat_engine.retrieval_query(question, turns))
            focused = []
            if focus and focus.get("commit"):
                try:
                    focused = get_commits(project["path"], 1, rev=git_ops.commit_detail(project["path"], focus["commit"])["hash"])
                except (RepoError, GitOpError):
                    focused = []
            candidates = chat_engine.candidate_commits([*focused, *hits], previous, follow_up)
            messages, used_full = chat_engine.build_messages(llm, question, candidates, turns, language, focus)
            used = [_commit_summary(x) for x in used_full]
            store.update_message(reply_id, commits=used)
            yield _sse({"type": "commits", "commits": used})
            yield _sse({"type": "status", "stage": "reading"})
            for piece in chat_engine.stream_answer(llm, messages):
                if not text:
                    store.update_message(reply_id, seconds=round(time.monotonic() - started, 1))
                    yield _sse({"type": "status", "stage": "answering"})
                text += piece
                yield _sse({"type": "token", "text": piece})
        store.update_message(reply_id, content=text)
        yield _sse({"type": "done", "seconds": round(time.monotonic() - started, 1)})
    except (ModelError, RepoError, GitOpError) as e:
        store.update_message(reply_id, content=text)
        yield _sse({"type": "error", "message": str(e)})
    finally:
        store.update_message(reply_id, content=text)  # keeps a stopped answer's words


async def ask(request: Request) -> Response:
    c = chat_or_404(request.path_params["cid"])
    project = project_or_404(c["project_id"])
    data = await body(request)
    question = str(data.get("question", "")).strip()
    if not question:
        return fail("Type a question first.")
    focus = data.get("focus") if isinstance(data.get("focus"), dict) else None
    if focus:
        focus = {k: str(focus.get(k) or "")[:20_000] for k in ("path", "commit", "text", "side")}
    return StreamingResponse(_answer_stream(c, project, question[:4000], focus), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# =========================================================================== app
async def index_page(request: Request) -> Response:
    return FileResponse(config.WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


def _http_error(request: Request, exc: HTTPException) -> Response:
    return fail(exc.detail, exc.status_code)


def create_app(setup: bool = True, extra_hosts: tuple[str, ...] = ()) -> Starlette:
    """Build the app. `setup` creates the demo project and fetches the editor; tests add their host name."""
    if setup:
        ensure_demo_project()
        ensure_editor()
    routes = [
        Route("/", index_page),
        Route("/api/health", health),
        Route("/api/heartbeat", heartbeat, methods=["POST"]),
        Route("/api/state", state),
        Route("/api/settings", update_settings, methods=["POST"]),
        Route("/api/jobs/{job_id}", job_status),
        Route("/api/model/download", download_model, methods=["POST"]),
        Route("/api/model", delete_model, methods=["DELETE"]),
        Route("/api/editor/download", download_editor, methods=["POST"]),
        Route("/api/projects", add_project, methods=["POST"]),
        Route("/api/projects/{pid:int}", update_project, methods=["PATCH"]),
        Route("/api/projects/{pid:int}", delete_project, methods=["DELETE"]),
        Route("/api/projects/{pid:int}/index", index_project, methods=["POST"]),
        Route("/api/projects/{pid:int}/commits", commits),
        Route("/api/projects/{pid:int}/commits/{sha}", commit_detail),
        Route("/api/projects/{pid:int}/commits/{sha}/file", commit_file),
        Route("/api/projects/{pid:int}/status", worktree_status),
        Route("/api/projects/{pid:int}/tree", worktree_tree),
        Route("/api/projects/{pid:int}/file", worktree_file, methods=["GET", "PUT"]),
        Route("/api/projects/{pid:int}/commit", make_commit, methods=["POST"]),
        Route("/api/projects/{pid:int}/chats", chats, methods=["GET", "POST"]),
        Route("/api/chats/{cid:int}", chat, methods=["PATCH", "DELETE"]),
        Route("/api/chats/{cid:int}/messages", chat_messages),
        Route("/api/chats/{cid:int}/ask", ask, methods=["POST"]),
        Mount("/static", StaticFiles(directory=config.WEB_DIR), name="static"),
        Mount("/monaco", StaticFiles(directory=config.VENDOR_DIR, check_dir=False), name="monaco"),
    ]
    middleware = [Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", *extra_hosts])]
    return Starlette(routes=routes, middleware=middleware, exception_handlers={HTTPException: _http_error})
