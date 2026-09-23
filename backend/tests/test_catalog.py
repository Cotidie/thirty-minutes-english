import json
from contextlib import asynccontextmanager

import pytest

from fastapi.testclient import TestClient
from mcp.types import CallToolResult, TextContent

from app.config import catalog as catalog_module
from app.config.catalog import Catalog, ModelOption, claude_models, newest_first, comfy_images, gemini_live, openai_text, openai_voice, openrouter_images
from app.config.settings import Settings
from app.db import Database
from app.db.costs import CostRepo
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
                {"value": "opus", "displayName": "Opus 5.5", "description": "Most capable", "supportsEffort": True, "supportedEffortLevels": ["low", "max"], "resolvedModel": "claude-opus-5-5"},
                {"value": "haiku", "displayName": "Haiku 4.5", "description": "Fastest"},
            ]}

    monkeypatch.setattr(catalog_module, "ClaudeSDKClient", FakeClient)
    assert claude_models({}) == [
        ModelOption("opus", "Opus 5.5", ("low", "max"), resolved="claude-opus-5-5"),
        ModelOption("haiku", "Haiku 4.5", ()),
    ]


def test_openai_lists_split_voice_from_text_and_drop_snapshots(http):
    http.json = {"data": [{"id": i} for i in [
        "gpt-live-1", "gpt-realtime-2", "gpt-live-transcribe", "gpt-realtime-2025-08-28",
        "gpt-5.6-luna", "gpt-5-codex", "gpt-image-2", "gpt-5-2025-08-07", "gpt-3.5-turbo-0125", "text-embedding-3", "o3",
    ]]}
    keys = {"OPENAI_API_KEY": "sk"}
    assert {o.id for o in openai_voice(keys)} == {"gpt-live-1", "gpt-realtime-2"}
    assert [o.id for o in openai_text(keys)] == ["gpt-5.6-luna"]
    assert http.requests[0].headers["Authorization"] == "Bearer sk"
    assert openai_voice({}) == []  # no key, no call


def test_gemini_lists_live_models_only(http):
    http.json = {"models": [
        {"name": "models/gemini-3.8-live", "displayName": "Gemini 3.8 Live", "description": "Live audio. More text.", "supportedGenerationMethods": ["bidiGenerateContent"]},
        {"name": "models/gemini-3.5-transcribe-live", "supportedGenerationMethods": ["bidiGenerateContent"]},
        {"name": "models/gemini-3-pro", "supportedGenerationMethods": ["generateContent"]},
    ]}
    assert gemini_live({"GEMINI_API_KEY": "AIza"}) == [ModelOption("gemini-3.8-live", "Gemini 3.8 Live")]


def test_openrouter_lists_image_models_by_id(http):
    http.json = {"data": [
        {"id": "z/img", "name": "Z", "description": "Draws. Well.", "pricing": {"prompt": "0.000002", "image_output": "0.00012"}},
        {"id": "a/img", "name": "A"},
    ]}
    z, a = openrouter_images({})
    assert [z.id, a.id] == ["z/img", "a/img"]
    assert (z.image_per_m, z.text_per_m) == (120.0, 2.0)
    assert (a.image_per_m, a.text_per_m) == (None, None)
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
                {"model_name": "xai/grok-image-generate", "tags": ["text-to-image"], "description": "Generates an image. Fast."},
                {"model_name": "bfl/flux-pro-fill", "tags": ["inpaint", "edit"]},
            ]}
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(data))])

    monkeypatch.setattr(catalog_module, "McpHttp", FakeServer)
    assert comfy_images({"COMFY_API_KEY": "c"}) == [
        ModelOption("vertexai/nano-banana-pro"),
        ModelOption("xai/grok-image-generate"),
    ]


def test_image_models_carry_what_a_picture_cost_here(tmp_path):
    db = Database(tmp_path / "s.db")
    for cost in (0.10, 0.20):
        db.costs.record("z/img", cost)
    for cost in [9.0] + [0.01] * CostRepo.RECENT:  # only the latest pictures count
        db.costs.record("a/img", cost)
    assert db.costs.per_picture() == {"z/img": (pytest.approx(0.15), 2), "a/img": (pytest.approx(0.01), CostRepo.RECENT)}

    cat = Catalog(db.caches, {"openrouter_images": lambda _: [ModelOption("z/img", image_per_m=120.0)]}, background=False)
    cat.refresh({})
    app = create_app(db, Services(FakeGenerator()), InlineExecutor(), env={}, catalog=cat)
    with TestClient(app) as c:
        image = {f["key"]: f for f in c.get("/api/settings").json()["fields"]}["IMAGE_MODEL"]
    z = next(o for o in image["variants"]["openrouter"]["options"] if o["id"] == "z/img")
    assert (z["image_per_m"], z["per_image"], z["per_image_count"]) == (120.0, pytest.approx(0.15), 2)


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


def test_the_menu_shows_the_newest_ten_plus_older_ones_asked_for(tmp_path):
    dated = [ModelOption(f"m{i}", created=float(i)) for i in range(12)]
    cat = catalog_with(tmp_path, {"x": lambda _: dated})
    cat.refresh({})
    assert [o.id for o in cat.options("x", {})] == [f"m{i}" for i in range(11, 1, -1)]
    assert [o.id for o in cat.options("x", {}, keep=("m0",))][-1] == "m0"  # the default or the saved one, with its details


def test_undated_lists_go_by_the_version_in_the_name_with_aliases_on_top():
    claude = [
        ModelOption("sonnet", "Sonnet", resolved="claude-sonnet-5"),
        ModelOption("haiku", "Haiku", resolved="claude-haiku-4-5-20251001"),
        ModelOption("opus", "Opus", resolved="claude-opus-5-5"),
        ModelOption("claude-fable-5-1", "Fable", resolved="claude-fable-5-1"),
    ]
    assert [o.id for o in newest_first(claude)] == ["opus", "claude-fable-5-1", "sonnet", "haiku"]
    gemini = [
        ModelOption("gemini-2.5-flash-native-audio-preview-09-2025"),
        ModelOption("gemini-3.8-live"),
        ModelOption("gemini-2.5-flash-native-audio-preview-12-2025"),
    ]
    assert [o.id for o in newest_first(gemini)] == [
        "gemini-3.8-live",
        "gemini-2.5-flash-native-audio-preview-12-2025",
        "gemini-2.5-flash-native-audio-preview-09-2025",
    ]
    comfy = [ModelOption("bfl/flux-pro-1.1-ultra"), ModelOption("qwen/qwen-image-3"), ModelOption("vertexai/nano-banana-pro")]
    assert [o.id for o in newest_first(comfy)] == ["vertexai/nano-banana-pro", "qwen/qwen-image-3", "bfl/flux-pro-1.1-ultra"]


def test_a_pinned_model_leads_its_menu_and_outlives_the_newest_ten(tmp_path):
    db = Database(tmp_path / "s.db")
    models = [ModelOption(f"m{i}", created=float(i)) for i in range(15)]
    cat = Catalog(db.caches, {"openrouter_images": lambda _: models}, background=False)
    cat.refresh({})
    app = create_app(db, Services(FakeGenerator()), InlineExecutor(), env={}, catalog=cat)

    def menu(view) -> list[tuple[str, bool]]:
        image = {f["key"]: f for f in view["fields"]}["IMAGE_MODEL"]["variants"]["openrouter"]
        assert image["catalog"] == "openrouter_images"
        return [(o["id"], o["pinned"]) for o in image["options"]]

    with TestClient(app) as c:
        pinned = menu(c.post("/api/settings/models/pin", json={"catalog": "openrouter_images", "model": "m1", "pinned": True}).json())
        assert pinned[0] == ("m1", True)  # m1 is far older than the newest ten
        assert pinned[1] == ("google/gemini-3-pro-image", False)  # the default, which this provider does not list
        assert [i for i, _ in pinned[2:12]] == [f"m{i}" for i in range(14, 4, -1)]

        unpinned = menu(c.post("/api/settings/models/pin", json={"catalog": "openrouter_images", "model": "m1", "pinned": False}).json())
        assert "m1" not in [i for i, _ in unpinned]


def test_a_list_cached_by_an_older_version_still_reads(tmp_path):
    db = Database(tmp_path / "s.db")
    db.caches.set_model_list("x", {"at": 1000.0, "options": [{"id": "m", "description": "dropped field", "efforts": ["low"]}]})
    assert Catalog(db.caches, {}, Clock()).options("x", {}) == [ModelOption("m", efforts=("low",))]
