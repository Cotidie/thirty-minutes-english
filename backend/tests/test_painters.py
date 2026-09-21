import base64
import json

import pytest

from app.mcp_client import McpError
from app.painters import ComfyPainter, OpenRouterPainter, fetch_url


class FakeMcp:
    def __init__(self, results: dict[str, list[dict]]):
        self.results = {tool: list(rs) for tool, rs in results.items()}
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, arguments))
        result = self.results[tool].pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def text(data) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


def test_comfy_submits_one_batch_waits_and_fetches_each_job_in_order():
    mcp = FakeMcp({
        "submit_batch": [text({"batch_id": "b1", "job_ids": ["j0", "j1", "j2"]})],
        "wait_for_batch": [text({"timed_out": True}), text({"timed_out": False})],
        "get_batch_output": [text({"outputs": [{"job_id": "j2", "url": "https://x/2"}, {"job_id": "j0", "url": "https://x/0"}]})],
    })
    fetched = []

    def fetch(url):
        fetched.append(url)
        if url.endswith("/2"):
            raise OSError("gone")
        return b"PNG" + url[-1].encode()

    pictures = ComfyPainter(mcp, "vertexai/nano-banana-2-lite", fetch=fetch).paint(["a", "b", "c"])

    assert pictures == [b"PNG0", None, None]
    submit = mcp.calls[0][1]
    assert submit["confirm"] is True
    assert [i["prompt"] for i in submit["items"]] == ["a", "b", "c"]
    assert submit["items"][0]["model"] == "vertexai/nano-banana-2-lite"
    assert [c[0] for c in mcp.calls] == ["submit_batch", "wait_for_batch", "wait_for_batch", "get_batch_output"]
    assert fetched == ["https://x/0", "https://x/2"]


def test_comfy_spells_an_openai_model_as_the_partner_slug_plus_variant():
    mcp = FakeMcp({
        "submit_batch": [text({"batch_id": "b", "job_ids": ["j0"]})],
        "wait_for_batch": [text({"timed_out": False})],
        "get_batch_output": [text({"outputs": []})],
    })
    ComfyPainter(mcp, "openai/gpt-image-2.5-flare", fetch=lambda u: b"").paint(["a"])
    item = mcp.calls[0][1]["items"][0]
    assert item["model"] == "openai/images-generations"
    assert item["params"] == {"model": "gpt-image-2.5-flare"}


def test_openrouter_decodes_the_inline_image_and_shrugs_off_a_failed_one():
    png = base64.b64encode(b"PNG1").decode()
    mcp = FakeMcp({
        "generate-image": [
            {"content": [{"type": "text", "text": "here"}, {"type": "image", "data": png, "mimeType": "image/png"}]},
            McpError("generate-image: over budget"),
            {"content": [{"type": "text", "text": "nothing"}]},
        ]
    })
    pictures = OpenRouterPainter(mcp, "google/gemini-3.1-flash-lite-image").paint(["a", "b", "c"])
    assert pictures == [b"PNG1", None, None]
    assert mcp.calls[0] == ("generate-image", {"prompt": "a", "model": "google/gemini-3.1-flash-lite-image"})


def test_fetch_retries_a_flaky_link(monkeypatch):
    import app.painters as mod

    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"PNG"

    def urlopen(url, timeout):
        calls.append(url)
        if calls.count(url) < 3:
            raise OSError("wrong version number")
        return Response()

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    assert fetch_url("https://img/1") == b"PNG"
    assert calls == ["https://img/1"] * 3
    with pytest.raises(OSError):
        fetch_url("https://img/2", attempts=2)
