import json
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from mcp.types import CallToolResult, TextContent

from app.config import catalog as catalog_module
from app.config.catalog import Catalog, ModelOption, claude_models, comfy_images, gemini_live, openai_text, openai_voice, openrouter_images
from app.config.settings import Settings
from app.db import Database
from app.main import create_app
from app.wiring import Services, effort
from tests.test_api import FakeGenerator, InlineExecutor


class Clock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def catalog_with(tmp_path, fetchers, clock=None) -> Catalog:
    return Catalog(Database(tmp_path / "s.db").caches, fetchers, clock or Clock(), background=False)


def test_a_missing_list_is_fetched_and_a_fresh_one_is_not(tmp_path):
    calls = []

    def fetch(keys):
        calls.append(keys["OPENAI_API_KEY"])
        return [ModelOption("gpt-live-1")]

    clock = Clock()
    cat = catalog_with(tmp_path, {"openai_voice": fetch}, clock)
    assert cat.options("openai_voice", {"OPENAI_API_KEY": "sk"}) == []  # answered from the (empty) cache; fetched after
    assert cat.options("openai_voice", {"OPENAI_API_KEY": "sk"}) == [ModelOption("gpt-live-1")]
    assert calls == ["sk"]

    clock.now += Catalog.TTL_S + 1
    cat.options("openai_voice", {"OPENAI_API_KEY": "sk"})
    assert calls == ["sk", "sk"]


def test_a_failed_or_empty_fetch_keeps_the_last_list(tmp_path):
    answers = [[ModelOption("a")], RuntimeError("provider down"), []]

    def fetch(_):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    cat = catalog_with(tmp_path, {"x": fetch})
    assert cat.refresh({}) == {}
    assert cat.refresh({}) == {"x": "provider down"}
    assert cat.refresh({}) == {}
    assert cat.options("x", {}) == [ModelOption("a")]


def test_efforts_come_from_the_claude_list(tmp_path):
    cat = catalog_with(tmp_path, {"claude": lambda _: [ModelOption("opus", efforts=("low", "max")), ModelOption("haiku", efforts=())]})
    cat.refresh({})
    assert cat.efforts_of("opus") == ("low", "max")
    assert cat.efforts_of("haiku") == ()
    assert cat.efforts_of("claude-unknown") is None


def test_a_model_without_effort_runs_without_one():
    levels = {"haiku": (), "opus": ("low", "xhigh")}
    assert effort(Settings({}, {"CLAUDE_MODEL": "haiku", "CLAUDE_EFFORT": "xhigh"}), "CLAUDE_EFFORT", levels.get) is None
    assert effort(Settings({}, {"CLAUDE_MODEL": "opus", "CLAUDE_EFFORT": "xhigh"}), "CLAUDE_EFFORT", levels.get) == "xhigh"
    assert effort(Settings({}, {"CLAUDE_MODEL": "new-model"}), "CLAUDE_EFFORT", levels.get) == "xhigh"


def test_claude_models_come_from_claude_code(monkeypatch):
    class FakeClient:
        def __init__(self, options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get_server_info(self):
            return {"models": [
                {"value": "opus", "displayName": "Opus 5.5", "description": "Most capable", "supportsEffort": True, "supportedEffortLevels": ["low", "max"]},
                {"value": "haiku", "displayName": "Haiku 4.5", "description": "Fastest"},
            ]}

    monkeypatch.setattr(catalog_module, "ClaudeSDKClient", FakeClient)
    assert claude_models({}) == [
        ModelOption("opus", "Opus 5.5", "Most capable", ("low", "max")),
        ModelOption("haiku", "Haiku 4.5", "Fastest", ()),
    ]


def test_openai_lists_split_voice_from_text_and_drop_snapshots(http):
    http.json = {"data": [{"id": i} for i in [
        "gpt-live-1", "gpt-realtime-2", "gpt-live-transcribe", "gpt-realtime-2025-08-28",
        "gpt-5.6-luna", "gpt-5-codex", "gpt-image-2", "gpt-5-2025-08-07", "gpt-3.5-turbo-0125", "text-embedding-3", "o3",
    ]]}
    keys = {"OPENAI_API_KEY": "sk"}
    assert [o.id for o in openai_voice(keys)] == ["gpt-live-1", "gpt-realtime-2"]
    assert [o.id for o in openai_text(keys)] == ["gpt-5.6-luna"]
    assert http.requests[0].headers["Authorization"] == "Bearer sk"
    assert openai_voice({}) == []  # no key, no call


def test_gemini_lists_live_models_only(http):
    http.json = {"models": [
        {"name": "models/gemini-3.8-live", "displayName": "Gemini 3.8 Live", "description": "Live audio. More text.", "supportedGenerationMethods": ["bidiGenerateContent"]},
        {"name": "models/gemini-3.5-transcribe-live", "supportedGenerationMethods": ["bidiGenerateContent"]},
        {"name": "models/gemini-3-pro", "supportedGenerationMethods": ["generateContent"]},
    ]}
    assert gemini_live({"GEMINI_API_KEY": "AIza"}) == [ModelOption("gemini-3.8-live", "Gemini 3.8 Live", "Live audio")]


def test_openrouter_lists_image_models_by_id(http):
    http.json = {"data": [{"id": "z/img", "name": "Z", "description": "Draws. Well."}, {"id": "a/img", "name": "A"}]}
    assert [o.id for o in openrouter_images({})] == ["a/img", "z/img"]
    assert "output_modalities=image" in str(http.requests[0].url)


def test_comfy_lists_text_to_image_partner_models(monkeypatch):
    class FakeServer:
        def __init__(self, url, key):
            pass

        @asynccontextmanager
        async def session(self):
            yield self

        async def call(self, tool, args):
            data = {"data": [
                {"model_name": "vertexai/nano-banana-pro", "tags": ["text-to-image"]},
                {"model_name": "xai/grok-image-generate", "tags": ["text-to-image"], "tiers": ["grok-imagine-image", "grok-imagine-image-pro"]},
                {"model_name": "bfl/flux-pro-fill", "tags": ["inpaint", "edit"]},
            ]}
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(data))])

    monkeypatch.setattr(catalog_module, "McpHttp", FakeServer)
    assert comfy_images({"COMFY_API_KEY": "c"}) == [
        ModelOption("vertexai/nano-banana-pro"),
        ModelOption("xai/grok-image-generate", description="Tiers: grok-imagine-image, grok-imagine-image-pro"),
    ]


def test_the_modal_gets_the_cached_models_with_the_default_kept_and_can_refresh(tmp_path):
    lists = {"claude": [ModelOption("sonnet", "Sonnet 5"), ModelOption("haiku", "Haiku 4.5", efforts=())]}
    db = Database(tmp_path / "s.db")
    cat = Catalog(db.caches, {"claude": lambda _: lists["claude"]}, background=False)
    app = create_app(db, Services(FakeGenerator()), InlineExecutor(), env={}, catalog=cat)
    with TestClient(app) as c:
        c.get("/api/settings")  # first open fetches in the background (inline here)
        field = {f["key"]: f for f in c.get("/api/settings").json()["fields"]}["CLAUDE_MODEL"]
        assert [o["id"] for o in field["options"]] == ["opus", "sonnet", "haiku"]  # default opus not listed: kept on top
        assert field["options"][2]["efforts"] == []

        lists["claude"] = [ModelOption("opus", "Opus 5.5")]
        refreshed = {f["key"]: f for f in c.post("/api/settings/models/refresh").json()["fields"]}["CLAUDE_MODEL"]
        assert [o["label"] for o in refreshed["options"]] == ["Opus 5.5"]
