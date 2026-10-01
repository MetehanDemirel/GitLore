"""Use a model served by another app on this computer instead of the built-in one.

Ollama (http://localhost:11434), LM Studio (http://localhost:1234), llama.cpp's llama-server (:8080) and
others offer the same OpenAI-style API: GET /v1/models and POST /v1/chat/completions. LocalServerLlm
speaks it and looks like llama_cpp.Llama to the rest of GitLore (tokenize, detokenize, streamed chat).

Only addresses on this computer are accepted: GitLore promises that code never leaves the machine.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from urllib.parse import urlsplit

from src.model_manager import ModelError

DEFAULT_URL = "http://localhost:11434"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_CHARS_PER_TOKEN = 4  # the server's tokenizer isn't exposed; a rough count keeps prompts inside the budget


def normalize_url(url: str) -> str:
    """'localhost:11434', 'http://127.0.0.1:1234/v1/' -> 'http://localhost:11434', 'http://127.0.0.1:1234'."""
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    if url.endswith("/v1"):
        url = url[:-3]
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in _LOCAL_HOSTS:
        raise ModelError("Enter a server on this computer, for example http://localhost:11434.")
    return url


def _request(url: str, payload: dict | None = None, timeout: float = 5):
    data = json.dumps(payload).encode() if payload is not None else None
    # Windows tries "localhost" as IPv6 first and waits ~2 s per refusal; model servers listen on 127.0.0.1.
    url = url.replace("://localhost", "://127.0.0.1", 1)
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if data else "GET")
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        raise ModelError(f"The local server answered {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise ModelError(f"Nothing is answering at {url.split('/v1')[0]}. Is the server running?") from None


def list_models(url: str) -> list[str]:
    """Model names the server offers (also a connection check)."""
    with _request(normalize_url(url) + "/v1/models") as r:
        data = json.load(r)
    return sorted(m["id"] for m in data.get("data", []) if m.get("id"))


class LocalServerLlm:
    def __init__(self, url: str, model: str) -> None:
        if not model:
            raise ModelError("Pick a model for the local server in Settings.")
        self.url, self.model = normalize_url(url), model
        # GitLore adds Qwen3's /no_think switch based on this, as for the built-in model.
        self.metadata = {"general.architecture": "qwen3"} if "qwen3" in model.lower() else {}

    def tokenize(self, data: bytes, add_bos: bool = False, special: bool = False) -> list[bytes]:
        # Chunks rather than ids, so detokenize can give the text back for truncation.
        return [data[i:i + _CHARS_PER_TOKEN] for i in range(0, len(data), _CHARS_PER_TOKEN)]

    def detokenize(self, tokens: list[bytes]) -> bytes:
        return b"".join(tokens)

    def create_chat_completion(self, messages: list[dict], stream: bool = True, max_tokens: int = 512,
                               temperature: float = 0.2, **_ignored) -> Iterator[dict]:
        """Streams chunks shaped like llama_cpp's: {"choices": [{"delta": {"content": ...}}]}."""
        payload = {"model": self.model, "messages": messages, "stream": True, "max_tokens": max_tokens,
                   "temperature": temperature}
        with _request(self.url + "/v1/chat/completions", payload, timeout=600) as r:  # a cold model loads slowly
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                chunk = json.loads(body)
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                yield {"choices": [{"delta": {"content": delta.get("content") or ""}}]}
