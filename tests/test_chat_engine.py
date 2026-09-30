from __future__ import annotations

import pytest

from src import chat_engine, config, model_manager
from src.git_parser import Commit


class FakeLlm:
    """1 token per 4 bytes; streams a canned answer."""

    def tokenize(self, data: bytes, add_bos: bool = False, special: bool = False) -> list[int]:
        return list(range((len(data) + 3) // 4))

    def detokenize(self, toks: list[int]) -> bytes:
        return b"x" * (len(toks) * 4)

    def create_chat_completion(self, **kwargs):
        assert kwargs["stream"] is True
        yield {"choices": [{"delta": {"role": "assistant"}}]}
        for word in ("Because ", "of ", "[abc1234]."):
            yield {"choices": [{"delta": {"content": word}}]}


def make_commit(i: int, diff_chars: int = 100) -> Commit:
    h = f"{i:07x}" + "0" * 33
    return Commit(hash=h, short_hash=h[:7], author=f"Dev {i}", date="2026-09-30T12:00:00+00:00",
                  message=f"Change number {i}", files_changed=[f"f{i}.py"], diff_summary="+" + "y" * diff_chars)


def total_tokens(llm, messages) -> int:
    return sum(len(llm.tokenize(m["content"].encode())) for m in messages)


def test_commits_are_included_in_rank_order_with_citation_format():
    llm = FakeLlm()
    commits = [make_commit(1), make_commit(2)]
    messages, used = chat_engine.build_messages(llm, "Why?", commits)

    assert used == commits
    assert messages[0] == {"role": "system", "content": chat_engine.SYSTEM_PROMPT}
    user = messages[-1]["content"]
    assert user.index("[0000001]") < user.index("[0000002]")
    assert "Dev 1, 2026-09-30" in user and "Files: f1.py" in user
    assert user.rstrip().endswith("Question: Why?")


def test_prompt_never_exceeds_context_budget():
    llm = FakeLlm()
    commits = [make_commit(i, diff_chars=1500) for i in range(50)]
    messages, used = chat_engine.build_messages(llm, "What happened?", commits)

    assert 0 < len(used) < 50
    assert total_tokens(llm, messages) <= config.MAX_PROMPT_TOKENS


def test_long_diffs_are_trimmed_in_the_prompt():
    c = make_commit(1, diff_chars=5000)
    block = chat_engine.format_commit(c)
    assert len(block) < config.PROMPT_DIFF_CHARS + 200
    assert block.endswith("(diff truncated)")


def test_falls_back_to_message_only_when_diff_does_not_fit(monkeypatch: pytest.MonkeyPatch):
    llm = FakeLlm()
    c = make_commit(1, diff_chars=500)
    with_diff = len(llm.tokenize(chat_engine.format_commit(c).encode()))
    without = len(llm.tokenize(chat_engine.format_commit(c, include_diff=False).encode()))
    fixed = total_tokens(llm, chat_engine.build_messages(llm, "Why?", [])[0])
    # Leave room for the message-only block but not the diff.
    monkeypatch.setattr(config, "MAX_PROMPT_TOKENS", fixed + 2 * 64 + (with_diff + without) // 2)

    messages, used = chat_engine.build_messages(llm, "Why?", [c])
    assert used == [c]
    assert "Change number 1" in messages[-1]["content"]
    assert "Diff:" not in messages[-1]["content"]


def test_follow_ups_keep_previous_commits_first():
    a, b, c = make_commit(1), make_commit(2), make_commit(3)
    assert chat_engine.candidate_commits([b, c], previous=[a, b], follow_up=True) == [a, b, c]
    assert chat_engine.candidate_commits([b, c], previous=[a], follow_up=False) == [b, c]
    assert chat_engine.is_follow_up("and who?", [("q", "a")])
    assert not chat_engine.is_follow_up("and who?", [])
    # A normal-length new question is not a follow-up, even mid-conversation.
    assert not chat_engine.is_follow_up("How are proxy settings read from environment variables?", [("q", "a")])


def test_no_commits_says_so():
    messages, used = chat_engine.build_messages(FakeLlm(), "Why?", [])
    assert used == []
    assert "No relevant commits" in messages[-1]["content"]


def test_history_is_carried_and_truncated():
    llm = FakeLlm()
    long_answer = "word " * 2000
    messages, _ = chat_engine.build_messages(llm, "and who?", [make_commit(1)], history=[("Why X?", long_answer)])
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "Why X?"
    assert len(llm.tokenize(messages[2]["content"].encode())) <= 210


def test_retrieval_query_for_follow_ups():
    history = [("Why did the login flow change?", "Because...")]
    assert chat_engine.retrieval_query("and who did that?", history) == "Why did the login flow change?\nand who did that?"
    long_q = "What changed in the CSV exporter when streaming support was added last year?"
    assert chat_engine.retrieval_query(long_q, history) == long_q
    assert chat_engine.retrieval_query("who?", []) == "who?"


def test_stream_answer_yields_only_content():
    assert "".join(chat_engine.stream_answer(FakeLlm(), [])) == "Because of [abc1234]."


_DEFAULT = config.MODEL_PRESETS[config.DEFAULT_PRESET]


@pytest.mark.skipif(not model_manager.is_downloaded(_DEFAULT), reason="default model not downloaded")
def test_real_model_answers_with_citation():
    llm = model_manager.load_llm(_DEFAULT)
    commit = Commit(hash="a1b2c3d" + "0" * 33, short_hash="a1b2c3d", author="Ada Lovelace",
                    date="2026-01-15T10:00:00+00:00",
                    message="Switch login to JWT tokens\n\nServer sessions did not scale across multiple pods.",
                    files_changed=["auth/login.py"], diff_summary="### auth/login.py\n-    session.save(user)\n+    return issue_jwt(user)")
    messages, used = chat_engine.build_messages(llm, "Why did the login flow change?", [commit])
    answer = "".join(chat_engine.stream_answer(llm, messages))
    assert used == [commit]
    assert "a1b2c3d" in answer
    assert any(w in answer.lower() for w in ("scale", "pods", "session"))


@pytest.mark.parametrize("pieces, expected", [
    (["<think>\n\n</think>\n\n", "Because ", "[a1b2c3d]."], "Because [a1b2c3d]."),     # Qwen3 /no_think
    (["<thi", "nk>plan it", "</th", "ink>\n", "Answer"], "Answer"),                   # tags split across chunks
    (["<think>long reasoning</think>Done"], "Done"),
    (["Plain ", "answer"], "Plain answer"),                                           # models that never think
    (["", "\n", "Hi"], "Hi"),
    (["I think <think> is a tag"], "I think <think> is a tag"),                       # only a *leading* block is removed
])
def test_think_blocks_are_stripped_from_the_stream(pieces, expected):
    assert "".join(chat_engine._strip_think(iter(pieces))) == expected


def test_qwen3_models_get_the_no_think_switch():
    class Qwen3(FakeLlm):
        metadata = {"general.architecture": "qwen3"}

    assert chat_engine.build_messages(Qwen3(), "Why?", [])[0][0]["content"].endswith("/no_think")
    assert "/no_think" not in chat_engine.build_messages(FakeLlm(), "Why?", [])[0][0]["content"]


def test_answer_language_is_requested_for_non_english():
    system = chat_engine.build_messages(FakeLlm(), "Neden?", [], language="tr")[0][0]["content"]
    assert "Always answer in Turkish" in system
    assert "Always answer in" not in chat_engine.build_messages(FakeLlm(), "Why?", [], language="en")[0][0]["content"]
    assert "Always answer in" not in chat_engine.build_messages(FakeLlm(), "Why?", [], language="xx")[0][0]["content"]


def test_selected_code_is_shown_before_the_question_and_budgeted():
    focus = {"path": "auth/login.py", "commit": "a1b2c3d4e5", "text": "return issue_jwt(user)"}
    messages, used = chat_engine.build_messages(FakeLlm(), "What does this do?", [make_commit(1)], focus=focus)
    user = messages[-1]["content"]
    assert "The user selected this code from auth/login.py in commit [a1b2c3d]" in user
    assert user.index("return issue_jwt(user)") < user.index("Question: What does this do?")

    huge = {"path": "x.py", "text": "z" * 50_000}
    messages, _ = chat_engine.build_messages(FakeLlm(), "?", [make_commit(i) for i in range(20)], focus=huge)
    assert total_tokens(FakeLlm(), messages) <= config.MAX_PROMPT_TOKENS
    assert messages[-1]["content"].count("z") == 1200
