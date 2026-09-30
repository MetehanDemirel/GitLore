"""Build token-budgeted prompts from retrieved commits and stream answers."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from src import config
from src.git_parser import Commit

if TYPE_CHECKING:
    from llama_cpp import Llama

SYSTEM_PROMPT = (
    "You are GitLore, an assistant that explains the history of a Git repository. "
    "Answer the user's question using ONLY the commits provided. "
    "Cite every claim with the commit's short hash in square brackets, e.g. [a1b2c3d], and name its author. "
    "Explain *why* a change was made only when the commit message or diff shows it; "
    "never invent reasons or details that are not in the commits. "
    "If the commits don't contain the answer, say so plainly. Be concise."
)

Turn = tuple[str, str]  # (question, answer)

_TEMPLATE_SLACK_TOKENS = 64      # chat-template markup around each message
_HISTORY_ANSWER_TOKENS = 200     # how much of the previous answer to carry into a follow-up
_FOLLOW_UP_MAX_WORDS = 5         # short questions ("and who did that?") inherit the previous question


def is_follow_up(question: str, history: Sequence[Turn] = ()) -> bool:
    """Short questions after a previous turn ("and who did that?") refer back to it."""
    return bool(history) and len(question.split()) <= _FOLLOW_UP_MAX_WORDS


def retrieval_query(question: str, history: Sequence[Turn] = ()) -> str:
    """Text to search the vector store with. Follow-ups borrow context from the previous question."""
    return f"{history[-1][0]}\n{question}" if is_follow_up(question, history) else question


def candidate_commits(hits: Sequence[Commit], previous: Sequence[Commit], follow_up: bool) -> list[Commit]:
    """Follow-ups keep the commits the previous answer was based on first, so the conversation stays on topic."""
    ranked = [*previous, *hits] if follow_up else list(hits)
    return list({c["hash"]: c for c in ranked}.values())


def format_commit(c: Commit, include_diff: bool = True) -> str:
    lines = [
        f"[{c['short_hash']}] {c['author']}, {c['date'][:10]}",
        f"Message: {c['message']}",
    ]
    if c["files_changed"]:
        lines.append(f"Files: {', '.join(c['files_changed'])}")
    if include_diff and c["diff_summary"]:
        diff = c["diff_summary"]
        if len(diff) > config.PROMPT_DIFF_CHARS:
            diff = diff[: config.PROMPT_DIFF_CHARS].rsplit("\n", 1)[0] + "\n… (diff truncated)"
        lines.append(f"Diff:\n{diff}")
    return "\n".join(lines)


def build_messages(
    llm: "Llama", question: str, commits: Sequence[Commit], history: Sequence[Turn] = ()
) -> tuple[list[dict], list[Commit]]:
    """Pack as many commits (best first) as fit the context budget.

    Returns the chat messages and the commits actually included (for citations in the UI).
    """

    def tokens(text: str) -> int:
        return len(llm.tokenize(text.encode("utf-8"), add_bos=False, special=False))

    system = SYSTEM_PROMPT
    if getattr(llm, "metadata", {}).get("general.architecture") == "qwen3":
        system += " /no_think"  # Qwen3's switch to skip its slow hidden reasoning step
    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        prev_q, prev_a = history[-1]
        prev_a = _truncate_to_tokens(llm, prev_a, _HISTORY_ANSWER_TOKENS)
        messages += [{"role": "user", "content": prev_q}, {"role": "assistant", "content": prev_a}]

    question_block = f"\n\nQuestion: {question.strip()}"
    budget = (
        config.MAX_PROMPT_TOKENS
        - _TEMPLATE_SLACK_TOKENS * (len(messages) + 1)
        - sum(tokens(m["content"]) for m in messages)
        - tokens("Commits:\n\n" + question_block)
    )

    blocks: list[str] = []
    used: list[Commit] = []
    for c in commits:
        for include_diff in (True, False):  # fall back to message + files if the diff doesn't fit
            block = format_commit(c, include_diff)
            cost = tokens(block + "\n\n")
            if cost <= budget:
                blocks.append(block)
                used.append(c)
                budget -= cost
                break

    context = "\n\n".join(blocks) if blocks else "(No relevant commits were found.)"
    messages.append({"role": "user", "content": f"Commits:\n\n{context}{question_block}"})
    return messages, used


def stream_answer(llm: "Llama", messages: list[dict]) -> Iterator[str]:
    """Yield answer text chunks, without any <think>…</think> block reasoning models emit first."""
    chunks = (
        chunk["choices"][0]["delta"].get("content") or ""
        for chunk in llm.create_chat_completion(
            messages=messages,
            stream=True,
            max_tokens=config.ANSWER_TOKENS,
            temperature=config.TEMPERATURE,
            repeat_penalty=1.1,
        )
    )
    yield from _strip_think(chunks)


def _strip_think(chunks: Iterator[str]) -> Iterator[str]:
    """Drop a leading <think>…</think> block (and the blank lines after it) from a text stream."""
    head = ""
    for piece in chunks:
        head += piece
        stripped = head.lstrip()
        if "<think>".startswith(stripped):  # still could be the opening tag
            continue
        if stripped.startswith("<think>"):
            if "</think>" not in stripped:
                continue
            stripped = stripped.split("</think>", 1)[1]
        head = stripped.lstrip()
        break
    if head:
        yield head
    for piece in chunks:
        if piece:
            yield piece


def _truncate_to_tokens(llm: "Llama", text: str, max_tokens: int) -> str:
    toks = llm.tokenize(text.encode("utf-8"), add_bos=False, special=False)
    if len(toks) <= max_tokens:
        return text
    return llm.detokenize(toks[:max_tokens]).decode("utf-8", errors="ignore") + " …"
