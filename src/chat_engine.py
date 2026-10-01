"""Build token-budgeted prompts from retrieved commits and stream answers."""

from __future__ import annotations

import re
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
    "Focus on WHY things changed, not just what: look for the reason in commit messages, the commits "
    "a revert undid, and related commits about the same issue number. "
    "Explain *why* a change was made only when the commit message or diff shows it; "
    "never invent reasons or details that are not in the commits. "
    "If the commits don't contain the answer, say so plainly. Be concise."
)

Turn = tuple[str, str]  # (question, answer)

# Language names as the model understands them best (in English).
ANSWER_LANGUAGES = {"en": "English", "tr": "Turkish", "fr": "French", "de": "German", "es": "Spanish",
                    "it": "Italian", "zh": "Simplified Chinese"}
_FOCUS_MAX_CHARS = 1200          # selected code carried into the prompt

_TEMPLATE_SLACK_TOKENS = 64      # chat-template markup around each message
_HISTORY_ANSWER_TOKENS = 200     # how much of the previous answer to carry into a follow-up
_FOLLOW_UP_MAX_WORDS = 5         # short questions ("and who did that?") inherit the previous question
_FOLLOW_UP_LONG_WORDS = 12       # ... and slightly longer ones that point back ("when was it added back?")
_REFERS_BACK = re.compile(r"\b(it|that|this|these|those|they|them|he|she|his|her|their|again|back|also|and)\b", re.I)


def is_follow_up(question: str, history: Sequence[Turn] = ()) -> bool:
    """Questions after a previous turn that are short, or point back to it ("when was it added back?")."""
    n = len(question.split())
    return bool(history) and (n <= _FOLLOW_UP_MAX_WORDS or (n <= _FOLLOW_UP_LONG_WORDS and bool(_REFERS_BACK.search(question))))


def retrieval_query(question: str, history: Sequence[Turn] = ()) -> str:
    """Text to search the vector store with. Follow-ups borrow context from the previous question."""
    return f"{history[-1][0]}\n{question}" if is_follow_up(question, history) else question


def candidate_commits(hits: Sequence[Commit], previous: Sequence[Commit], follow_up: bool) -> list[Commit]:
    """Follow-ups keep the commits the previous answer was based on first, so the conversation stays on topic."""
    ranked = [*previous, *hits] if follow_up else list(hits)
    return list({c["hash"]: c for c in ranked}.values())


def format_commit(c: Commit, include_diff: bool = True) -> str:
    # Labeled fields: a small model reads "Author: Sara" reliably; a bare "[hash] Sara, date" header it overlooks.
    lines = [
        f"Commit [{c['short_hash']}]",
        f"Author: {c['author']}",
        f"Date: {c['date'][:10]}",
        f"Message: {c['message'].strip()}",
    ]
    if c["files_changed"]:
        lines.append(f"Files: {', '.join(c['files_changed'])}")
    if include_diff and c["diff_summary"]:
        diff = c["diff_summary"]
        if len(diff) > config.PROMPT_DIFF_CHARS:
            diff = diff[: config.PROMPT_DIFF_CHARS].rsplit("\n", 1)[0] + "\n… (diff truncated)"
        lines.append(f"Diff:\n{diff}")
    return "\n".join(lines)


def format_focus(focus: dict) -> str:
    """The code the user selected (right-click → Ask GitLore), shown to the model before the question.

    Small models don't connect "selected code" with "the commit that changed it" on their own, so the
    link is stated explicitly: which commit added (right side) or removed (left side) the code.
    """
    path = focus.get("path") or "a file"
    text = (focus.get("text") or "")[:_FOCUS_MAX_CHARS]
    commit = (focus.get("commit") or "")[:7]
    if commit:
        verb = "removed" if focus.get("side") == "original" else "added"
        intro = (f"The user selected this code from {path}. Commit [{commit}] {verb} it "
                 f"(that commit is listed first above; use its message to explain why)")
    else:
        intro = f"The user selected this code from {path} (their current, uncommitted version)"
    return f"\n\n{intro}:\n```\n{text}\n```"


def build_messages(
    llm: "Llama", question: str, commits: Sequence[Commit], history: Sequence[Turn] = (),
    language: str = "en", focus: dict | None = None, notes: str = "",
) -> tuple[list[dict], list[Commit]]:
    """Pack as many commits (best first) as fit the context budget.

    `language` is the answer language; `focus` is code the user selected (path, commit, text).
    Returns the chat messages and the commits actually included (for citations in the UI).
    """

    def tokens(text: str) -> int:
        return len(llm.tokenize(text.encode("utf-8"), add_bos=False, special=False))

    system = SYSTEM_PROMPT
    if getattr(llm, "metadata", {}).get("general.architecture") == "qwen3":
        system += " /no_think"  # Qwen3's switch to skip its slow hidden reasoning step
    if language != "en" and language in ANSWER_LANGUAGES:
        system += f" Always answer in {ANSWER_LANGUAGES[language]}, even if the commits are in English."
    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        prev_q, prev_a = history[-1]
        prev_a = _truncate_to_tokens(llm, prev_a, _HISTORY_ANSWER_TOKENS)
        messages += [{"role": "user", "content": prev_q}, {"role": "assistant", "content": prev_a}]

    focus_block = format_focus(focus) if focus and focus.get("text") else ""
    # Small models follow the instruction closest to the end best, so the answer language is repeated here.
    reminder = f"\n(Answer in {ANSWER_LANGUAGES[language]}.)" if language != "en" and language in ANSWER_LANGUAGES else ""
    notes_block = f"\n\nDiscussion behind these changes (from GitHub):\n{notes[:1200]}" if notes else ""
    # Small models follow the instructions nearest the end, so the essentials are restated after the question.
    label = f"Follow-up question (about: {history[-1][0].strip()})" if is_follow_up(question, history) else "Question"
    rules = ("\n(Answer this exact question, not an earlier one. Use only the commits above and cite each claim "
             "with its hash in square brackets.)")
    question_block = f"{notes_block}{focus_block}\n\n{label}: {question.strip()}{rules}{reminder}"
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

    # Most relevant first. (Tried oldest-first: the eval got worse, the model then answers about whatever
    # sits last, e.g. "who reverted it?" described the later re-add.)
    context = "\n\n".join(blocks) if blocks else "(No relevant commits were found.)"
    messages.append({"role": "user", "content": f"Commits (most relevant first):\n\n{context}{question_block}"})
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
