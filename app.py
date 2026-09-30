"""GitLore — Streamlit entry point. Run with: streamlit run app.py"""

from __future__ import annotations

import gc
import json
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

import streamlit as st

from src import chat_engine, config, model_manager, vector_store
from src.config import ModelPreset
from src.git_parser import Commit, RepoError, commit_url_base, get_commits
from src.model_manager import ModelError

st.set_page_config(
    page_title="GitLore",
    page_icon=":material/history_edu:",
    layout="centered",
    initial_sidebar_state="expanded",
)

SETTINGS_FILE = config.DATA_DIR / "settings.json"
EMBEDDER_CACHE = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2"
COMMIT_COUNT_OPTIONS = [100, 200, 500, 1000, 2000]
EXAMPLE_QUESTIONS = [
    "What were the most significant recent changes?",
    "Why was the project structure changed?",
    "Which bugs were fixed most recently?",
]
ASSISTANT_AVATAR = ":material/history_edu:"
USER_AVATAR = ":material/person:"


# --------------------------------------------------------------------------- lifecycle
@st.cache_resource
def _start_idle_shutdown() -> bool:
    """Exit the whole app once the last browser tab has been closed for a while.

    Uses Streamlit's internal session manager; if that API ever changes, auto-shutdown quietly
    turns itself off (closing the terminal still stops everything). Set GITLORE_NO_AUTO_SHUTDOWN=1 to disable.
    """
    if os.environ.get("GITLORE_NO_AUTO_SHUTDOWN"):
        return False

    def watch() -> None:
        from streamlit.runtime import Runtime

        seen_session, idle_since = False, None
        while True:
            time.sleep(2)
            try:
                active = Runtime.instance()._session_mgr.num_active_sessions()
            except Exception:
                return
            if active:
                seen_session, idle_since = True, None
            elif seen_session:
                idle_since = idle_since or time.monotonic()
                if time.monotonic() - idle_since > config.IDLE_SHUTDOWN_SECONDS:
                    os._exit(0)

    threading.Thread(target=watch, name="gitlore-idle-shutdown", daemon=True).start()
    return True


# --------------------------------------------------------------------------- settings
def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(**changes) -> None:
    data = load_settings() | changes
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # remembering settings is a convenience, never an error


# --------------------------------------------------------------------------- shared UI
def confirm(title: str, message: str, action: str, on_confirm: Callable[[], None]) -> None:
    """Open a confirmation dialog for a destructive action."""

    @st.dialog(title)
    def dialog() -> None:
        st.write(message)
        with st.container(horizontal=True, horizontal_alignment="right"):
            if st.button("Cancel"):
                st.rerun()
            if st.button(action, type="primary"):
                on_confirm()

    dialog()


def status_row(label: str, manage: Callable[[], None], manage_help: str) -> None:
    """A '[✓ Ready · detail]  Manage' row used by both side-panel sections."""
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        st.badge(label, icon=":material/check:", color="green")
        # No icon: Streamlit exposes icon glyph names to screen readers ("tune Manage").
        with st.popover("Manage", help=manage_help, type="tertiary"):
            manage()


# --------------------------------------------------------------------------- model
@st.cache_resource(max_entries=1, show_spinner=False)
def get_llm(repo_id: str, filename: str):
    return model_manager.load_llm(ModelPreset(label="", repo_id=repo_id, filename=filename, size_gb=0))


def download_with_progress(preset: ModelPreset) -> None:
    """Download on a worker thread so the progress bar can update from the script thread."""
    state: dict = {}

    def work() -> None:
        try:
            model_manager.ensure_model(preset, on_progress=lambda d, t: state.update(done=d, total=t))
        except ModelError as e:
            state["error"] = str(e)

    bar = st.progress(0.0, text="Connecting to Hugging Face…")
    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        if state.get("total"):
            done, total = state["done"], state["total"]
            bar.progress(min(done / total, 1.0), text=f"Downloading… {done / 1e9:.2f} / {total / 1e9:.2f} GB")
        time.sleep(0.25)
    bar.empty()
    if "error" in state:
        st.error(state["error"])
    else:
        st.rerun()


def remove_model(preset: ModelPreset) -> None:
    get_llm.clear()  # release the memory-mapped file first (Windows can't delete open files)
    gc.collect()
    try:
        model_manager.delete_model(preset)
    except PermissionError:
        st.error("The model file is still in use. Restart GitLore, then remove it again.")
        return
    st.rerun()


def model_section(settings: dict) -> ModelPreset | None:
    st.subheader("Model")
    keys = [*config.MODEL_PRESETS, "custom"]
    labels = {k: p.label for k, p in config.MODEL_PRESETS.items()} | {"custom": "Custom GGUF from Hugging Face"}
    saved = settings.get("preset", config.DEFAULT_PRESET)
    choice = st.selectbox(
        "Model", keys, index=keys.index(saved) if saved in keys else 0,
        format_func=labels.get, label_visibility="collapsed",
    )
    if choice != saved:
        save_settings(preset=choice)

    if choice == "custom":
        repo_id = st.text_input("Hugging Face repo", value=settings.get("custom_repo", ""), placeholder="e.g. owner/model-GGUF…")
        filename = st.text_input("File name", value=settings.get("custom_file", ""), placeholder="e.g. model-Q4_K_M.gguf…")
        if not (repo_id and filename):
            st.caption("Enter a repo and a .gguf file name.")
            return None
        try:
            preset = model_manager.custom_preset(repo_id, filename)
        except ModelError as e:
            st.caption(str(e))
            return None
        save_settings(custom_repo=preset.repo_id, custom_file=preset.filename)
    else:
        preset = config.MODEL_PRESETS[choice]

    if model_manager.is_downloaded(preset):
        path = model_manager.model_path(preset)

        def manage() -> None:
            st.caption(str(path))
            if st.button("Remove from Disk", icon=":material/delete:", type="tertiary"):
                confirm("Remove Model?",
                        f"This deletes **{path.name}** ({path.stat().st_size / 1e9:.1f} GB). "
                        "You can download it again later.",
                        "Remove", lambda: remove_model(preset))

        status_row(f"Ready · {path.stat().st_size / 1e9:.1f} GB", manage, "Manage the model file")
        return preset

    size_note = f"{preset.size_gb:.1f} GB · " if preset.size_gb else ""
    st.caption(f"Not downloaded yet · {size_note}one-time download")
    if st.button("Download Model", type="primary", icon=":material/download:", width="stretch"):
        download_with_progress(preset)
    return None


# --------------------------------------------------------------------------- repository
def safe_count(path: str) -> int | None:
    """Indexed commit count for a repo, or None if the path isn't a usable repo."""
    try:
        return vector_store.count(path)
    except RepoError:
        return None


def index_repository(path: str, max_commits: int, rebuild: bool = False) -> None:
    try:
        commits = get_commits(path, max_commits)
        if rebuild:
            vector_store.reset(path)
    except RepoError as e:
        st.error(str(e))
        return

    first_run = not EMBEDDER_CACHE.exists()
    bar = st.progress(0.0, text="Preparing search model (first run only, ~80 MB)…" if first_run else "Checking for new commits…")
    added = vector_store.index_commits(
        path, commits, on_progress=lambda d, t: bar.progress(d / t, text=f"Indexing commits… {d} / {t}")
    )
    bar.empty()
    save_settings(repo_path=path, commit_count=max_commits)
    st.toast(f"Indexed {added} new commit{'s' if added != 1 else ''}." if added else "Index is already up to date.")
    st.rerun()


def repository_section(settings: dict) -> str | None:
    st.subheader("Repository")
    path = st.text_input(
        "Local repository folder", value=settings.get("repo_path", ""),
        placeholder=r"e.g. C:\projects\my-app…" if os.name == "nt" else "e.g. ~/projects/my-app…",
    ).strip().strip('"')
    saved_count = settings.get("commit_count", config.DEFAULT_COMMIT_COUNT)
    max_commits = st.select_slider(
        "Commits to index", COMMIT_COUNT_OPTIONS,
        value=saved_count if saved_count in COMMIT_COUNT_OPTIONS else config.DEFAULT_COMMIT_COUNT,
        help="Most recent commits first. Indexing runs at roughly 25–30 commits per second on a typical laptop.",
    )
    if not path:
        st.caption("Paste the path to a folder that contains a Git repository.")
        return None

    indexed = safe_count(path)
    if indexed:
        def manage() -> None:
            st.caption("Rebuild if the history was rewritten (rebase, force-push).")
            if st.button("Rebuild from Scratch", icon=":material/restart_alt:", type="tertiary"):
                confirm("Rebuild Index?",
                        f"This deletes the index of **{indexed:,} commits** and indexes the repository again.",
                        "Rebuild", lambda: index_repository(path, max_commits, rebuild=True))

        status_row(f"{indexed:,} commits indexed", manage, "Manage the index")

    label = "Update Index" if indexed else "Index Repository"
    if st.button(label, type="secondary" if indexed else "primary", icon=":material/manage_search:", width="stretch"):
        index_repository(path, max_commits)
    return path if indexed else None


# --------------------------------------------------------------------------- chat rendering
_CITATION_RE = re.compile(r"\[([0-9a-f]{7,40})\]")


def format_answer(text: str, url_base: str | None) -> str:
    """Turn [a1b2c3d] citations into code-styled hashes, linked to GitHub/GitLab when possible."""

    def link(m: re.Match) -> str:
        h = m.group(1)[:7]
        return f"[`{h}`]({url_base}{m.group(1)})" if url_base else f"`{h}`"

    return _CITATION_RE.sub(link, text)


def render_sources(commits: list[Commit], url_base: str | None) -> None:
    for c in commits:
        title = c["message"].splitlines()[0][:100]
        hash_md = f"[`{c['short_hash']}`]({url_base}{c['hash']})" if url_base else f"`{c['short_hash']}`"
        files = len(c["files_changed"])
        st.markdown(
            f"{hash_md}  {title}  \n"
            f":gray[{c['author']} · {c['date'][:10]} · {files} file{'s' if files != 1 else ''}]"
        )


def sources_label(commits: list[Commit], seconds: float | None = None) -> str:
    label = f"Used {len(commits)} commit{'s' if len(commits) != 1 else ''}"
    return f"{label} · {seconds:.0f} s" if seconds is not None else label


def render_history(url_base: str | None) -> None:
    for m in st.session_state.messages:
        if m["role"] == "user":
            with st.chat_message("user", avatar=USER_AVATAR):
                st.markdown(m["content"])
            continue
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            if m["commits"]:
                with st.expander(sources_label(m["commits"], m.get("seconds")), type="compact"):
                    render_sources(m["commits"], url_base)
            st.markdown(format_answer(m["content"], url_base) or ":gray[Stopped before the first words.]")


def conversation_history() -> tuple[list[chat_engine.Turn], list[Commit]]:
    msgs = st.session_state.messages
    turns = [(q["content"], a["content"]) for q, a in zip(msgs[::2], msgs[1::2])]
    previous = msgs[-1]["commits"] if msgs and msgs[-1]["role"] == "assistant" else []
    return turns, previous


def answer(question: str, repo: str, preset: ModelPreset, url_base: str | None) -> None:
    history, previous = conversation_history()
    # Record the turn up front and fill it in while streaming, so a stopped answer keeps what it has.
    reply = {"role": "assistant", "content": "", "commits": [], "seconds": None}
    st.session_state.messages += [{"role": "user", "content": question, "commits": []}, reply]

    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        started = time.monotonic()
        with st.status(":shimmer[Searching commit history…]", type="compact") as progress:
            with st.status("Loading model…", type="step") as step:
                try:
                    llm = get_llm(preset.repo_id, preset.filename)
                except ModelError as e:
                    step.update(label=str(e), state="error")
                    progress.update(label="Could not load the model", state="error")
                    return
                step.update(label="Model loaded", state="complete")
                st.caption(preset.label)

            with st.status("Searching commits…", type="step") as step:
                follow_up = chat_engine.is_follow_up(question, history)
                hits = vector_store.search(repo, chat_engine.retrieval_query(question, history))
                candidates = chat_engine.candidate_commits(hits, previous, follow_up)
                messages, used = chat_engine.build_messages(llm, question, candidates, history)
                reply["commits"] = used
                step.update(label=f"Found {len(used)} relevant commit{'s' if len(used) != 1 else ''}", state="complete")
                render_sources(used, url_base)

            with st.status(f"Reading {len(used)} commits… first words take 10–20 s on a CPU", type="step") as step:
                stream = chat_engine.stream_answer(llm, messages)
                reply["content"] = next(stream, "")
                reply["seconds"] = time.monotonic() - started
                step.update(label=f"Read in {reply['seconds']:.0f} s", state="complete")
            progress.update(label=sources_label(used, reply["seconds"]), state="complete", expanded=False)

        placeholder = st.empty()
        for piece in stream:
            reply["content"] += piece
            placeholder.markdown(format_answer(reply["content"], url_base) + " ▍")
        placeholder.markdown(format_answer(reply["content"], url_base))


def onboarding(model_ready: bool, repo_ready: bool) -> None:
    def step(done: bool, title: str, detail: str) -> None:
        icon = ":green[:material/check_circle:]" if done else ":gray[:material/radio_button_unchecked:]"
        st.markdown(f"{icon} **{title}**  \n:gray[{detail}]")

    with st.container(border=True):
        st.markdown("#### Get Started")
        step(model_ready, "Download a Model",
             "Choose a model in the side panel. The default is about 1 GB and runs on any modern CPU.")
        step(repo_ready, "Index a Repository",
             "Paste the path to a local Git repository and index its history.")
        st.caption("Everything runs on this computer. No account, API key or internet connection is needed after setup.")


# --------------------------------------------------------------------------- page
def main() -> None:
    _start_idle_shutdown()
    settings = load_settings()
    st.session_state.setdefault("messages", [])

    with st.sidebar:
        preset = model_section(settings)
        repo = repository_section(settings)
        if st.session_state.messages and st.button("Clear Conversation", icon=":material/delete_sweep:", type="tertiary"):
            def clear() -> None:
                st.session_state.messages = []
                st.rerun()

            confirm("Clear Conversation?", "This removes all questions and answers from this session.", "Clear", clear)
        st.caption("Runs locally on your CPU. Nothing leaves this computer.")

    # A different repository means a different conversation.
    if st.session_state.get("active_repo") != repo:
        st.session_state.active_repo = repo
        st.session_state.messages = []

    st.title("GitLore")
    st.caption("Ask how and why your code changed. Answers cite the commits they come from.")

    ready = preset is not None and repo is not None
    if not ready:
        onboarding(preset is not None, repo is not None)
        st.chat_input("Finish setup in the side panel to start asking…", disabled=True)
        return

    url_base = commit_url_base(repo)
    render_history(url_base)

    suggestion = None
    welcome = st.empty()
    if not st.session_state.messages:
        with welcome.container():
            st.caption(f"Ready · {Path(repo).name}")
            suggestion = st.pills("Try Asking", EXAMPLE_QUESTIONS, label_visibility="collapsed", key="suggestion")

    question = st.chat_input("Ask about this repository's history…", submit_mode="stop") or suggestion
    if question:
        welcome.empty()
        answer(question, repo, preset, url_base)


main()
