"""The local model server client, against a tiny fake OpenAI-compatible server on 127.0.0.1."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src import chat_engine, local_server
from src.model_manager import ModelError


class _Fake(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "qwen3:1.7b"}, {"id": "llama3.2"}]}).encode()
        self.send_response(200 if self.path == "/v1/models" else 404)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        _Fake.seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in ["Because ", "of [abc1234]."]:
            self.wfile.write(f'data: {json.dumps({"choices": [{"delta": {"content": piece}}]})}\n\n'.encode())
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_lists_models(server):
    assert local_server.list_models(server + "/v1/") == ["llama3.2", "qwen3:1.7b"]


def test_streams_an_answer_through_the_normal_pipeline(server):
    llm = local_server.LocalServerLlm(server, "qwen3:1.7b")
    messages, _ = chat_engine.build_messages(llm, "Why?", [])
    assert messages[0]["content"].endswith("/no_think")  # Qwen3 by name gets the same switch
    assert "".join(chat_engine.stream_answer(llm, messages)) == "Because of [abc1234]."
    assert _Fake.seen[-1]["model"] == "qwen3:1.7b" and _Fake.seen[-1]["stream"] is True


def test_truncation_round_trips_text():
    llm = local_server.LocalServerLlm("http://localhost:11434", "m")
    assert chat_engine._truncate_to_tokens(llm, "x" * 100, 5) == "x" * 20 + " …"


@pytest.mark.parametrize("url, expected", [
    ("localhost:11434", "http://localhost:11434"),
    ("http://127.0.0.1:1234/v1/", "http://127.0.0.1:1234"),
])
def test_normalize_url(url, expected):
    assert local_server.normalize_url(url) == expected


@pytest.mark.parametrize("url", ["http://example.com:11434", "http://192.168.1.5:11434", "file:///etc/passwd", ""])
def test_only_this_computer_is_allowed(url):
    with pytest.raises(ModelError):
        local_server.normalize_url(url)


def test_friendly_error_when_nothing_is_running():
    with pytest.raises(ModelError, match="Is the server running"):
        local_server.list_models("http://127.0.0.1:9")
