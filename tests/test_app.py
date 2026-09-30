"""UI tests: run app.py headlessly with Streamlit's AppTest (no browser, no server)."""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src import config, model_manager

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def isolated_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITLORE_NO_AUTO_SHUTDOWN", "1")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "data" / "models")
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "data" / "chroma")
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch):
    """Pretend the default model is downloaded, and answer with a canned stream."""
    from test_chat_engine import FakeLlm

    path = model_manager.model_path(config.MODEL_PRESETS[config.DEFAULT_PRESET])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"GGUF")
    monkeypatch.setattr(model_manager, "load_llm", lambda preset: FakeLlm())


def run_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    return at


def buttons(at: AppTest) -> list[str]:
    return [b.label for b in at.button]


def test_first_run_shows_onboarding_and_disabled_chat():
    at = run_app()
    assert "Download Model" in buttons(at)
    assert any("Get Started" in m.value for m in at.markdown)
    assert at.chat_input[0].disabled


def test_bad_repo_path_shows_error_with_next_step(fake_model, tmp_path: Path):
    at = run_app()
    at.text_input[0].set_value(str(tmp_path)).run()
    next(b for b in at.button if b.label == "Index Repository").click().run()

    assert not at.exception
    assert "Not a Git repository" in at.error[0].value
    assert "contains the .git directory" in at.error[0].value


def test_index_then_ask_a_question(fake_model, rb):
    rb.commit("Switch login to JWT tokens", {"auth.py": "jwt = True\n"})
    rb.commit("Fix README typo", {"README.md": "# Hi\n"})

    at = run_app()
    at.text_input[0].set_value(str(rb.path)).run()
    next(b for b in at.button if b.label == "Index Repository").click().run()
    assert not at.exception
    assert "Update Index" in buttons(at)
    assert not at.chat_input[0].disabled
    pills = at.get("button_group")
    assert len(pills) == 1 and "Why was the project structure changed?" in str(pills[0].proto)

    at.chat_input[0].set_value("Why did login change?").run()
    assert not at.exception
    messages = at.session_state["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Because of [abc1234]."
    assert messages[1]["commits"], "the answer should record which commits it used"
