"""Build token-budgeted prompts from retrieved commits and stream answers (Phase 5)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from src.git_parser import Commit

if TYPE_CHECKING:
    from llama_cpp import Llama

SYSTEM_PROMPT = (
    "You are GitLore, an assistant analyzing a Git repository. "
    "Answer using ONLY the commits below. "
    "Cite the short commit hash and author for every claim. "
    "If the commits don't answer the question, say so."
)


def build_messages(llm: "Llama", question: str, commits: list[Commit]) -> tuple[list[dict], list[Commit]]:
    """Pack as many commits as fit the context budget.

    Returns the chat messages and the commits actually included (for citations in the UI).
    """
    raise NotImplementedError("Phase 5")


def stream_answer(llm: "Llama", messages: list[dict]) -> Iterator[str]:
    """Yield answer text chunks for st.write_stream."""
    raise NotImplementedError("Phase 5")
