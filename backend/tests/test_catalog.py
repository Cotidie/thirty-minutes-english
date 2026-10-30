
import pytest

from tests.conftest import admin_client

from app.config import catalog as catalog_module
from app.config.catalog import Catalog, ModelOption, claude_models, gemini_live, newest_first, openrouter_images
from app.config.settings import Settings
from app.db import Database
from app.db.pictures import PictureRepo, PictureStat
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
        calls.append(keys["GEMINI_API_KEY"])
        return [ModelOption("gemini-3.8-live")]

    clock = Clock()
    cat = catalog_with(tmp_path, {"gemini_live": fetch}, clock)
    assert cat.options("gemini_live", {"GEMINI_API_KEY": "AIza"}) == []  # answered from the (empty) cache; fetched after
    assert cat.options("gemini_live", {"GEMINI_API_KEY": "AIza"}) == [ModelOption("gemini-3.8-live")]
    assert calls == ["AIza"]

    clock.now += Catalog.TTL_S + 1
    cat.options("gemini_live", {"GEMINI_API_KEY": "AIza"})
    assert calls == ["AIza", "AIza"]


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


def test_image_models_carry_what_a_picture_cost_and_took_here(tmp_path):
    db = Database(tmp_path / "s.db")
    for seconds, cost in ((10, 0.10), (None, 0.20), (20, None)):
        db.pictures.add("z/img", seconds, cost)
    for cost in [9.0] + [0.01] * PictureRepo.RECENT:  # only the latest pictures count
        db.pictures.add("a/img", 5, cost)
    assert db.pictures.stats() == {
        "z/img": PictureStat(pytest.approx(15), pytest.approx(0.15)),
        "a/img": PictureStat(5, pytest.approx(0.01)),
    }

    cat = Catalog(db.caches, {"openrouter_images": lambda _: [ModelOption("z/img", image_per_m=120.0)]}, background=False)
    cat.refresh({})
    app = create_app(db, Services(FakeGenerator()), InlineExecutor(), env={}, catalog=cat)
    with admin_client(app) as c:
        image = {f["key"]: f for f in c.get("/api/settings").json()["fields"]}["IMAGE_MODEL"]
    z = next(o for o in image["options"] if o["id"] == "z/img")
    assert (z["image_per_m"], z["per_image"], z["seconds_per_image"]) == (120.0, pytest.approx(0.15), pytest.approx(15))


def test_the_modal_gets_the_cached_models_with_the_default_kept_and_can_refresh(tmp_path):
    lists = {"claude": [ModelOption("sonnet", "Sonnet 5"), ModelOption("haiku", "Haiku 4.5", efforts=())]}
    db = Database(tmp_path / "s.db")
    cat = Catalog(db.caches, {"claude": lambda _: lists["claude"]}, background=False)
    app = create_app(db, Services(FakeGenerator()), InlineExecutor(), env={}, catalog=cat)
    with admin_client(app) as c:
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
    assert len(cat.options("x", {}, limit=None)) == 12  # an inline list shows all


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
    undated = [ModelOption("black-forest-labs/flux-pro-1.1-ultra"), ModelOption("qwen/qwen-image-3"), ModelOption("google/nano-banana-pro")]
    assert [o.id for o in newest_first(undated)] == ["google/nano-banana-pro", "qwen/qwen-image-3", "black-forest-labs/flux-pro-1.1-ultra"]


def test_a_pinned_model_leads_its_menu(tmp_path):
    db = Database(tmp_path / "s.db")
    models = [ModelOption(f"m{i}", created=float(i)) for i in range(15)]
    cat = Catalog(db.caches, {"openrouter_images": lambda _: models}, background=False)
    cat.refresh({})
    app = create_app(db, Services(FakeGenerator()), InlineExecutor(), env={}, catalog=cat)

    def menu(view) -> list[tuple[str, bool]]:
        image = {f["key"]: f for f in view["fields"]}["IMAGE_MODEL"]
        assert image["catalog"] == "openrouter_images"
        return [(o["id"], o["pinned"]) for o in image["options"]]

    with admin_client(app) as c:
        pinned = menu(c.post("/api/settings/models/pin", json={"catalog": "openrouter_images", "model": "m1", "pinned": True}).json())
        assert pinned[0] == ("m1", True)
        assert pinned[1] == ("google/gemini-3-pro-image", False)  # the default, which this provider does not list
        assert [i for i, _ in pinned[2:]] == [f"m{i}" for i in range(14, -1, -1) if i != 1]  # the inline list shows all

        unpinned = menu(c.post("/api/settings/models/pin", json={"catalog": "openrouter_images", "model": "m1", "pinned": False}).json())
        assert unpinned[0] == ("google/gemini-3-pro-image", False) and ("m1", False) in unpinned  # back in date order


def test_a_list_cached_by_an_older_version_still_reads(tmp_path):
    db = Database(tmp_path / "s.db")
    db.caches.set_model_list("x", 1000.0, [{"id": "m", "description": "dropped field", "efforts": ["low"]}])
    assert Catalog(db.caches, {}, Clock()).options("x", {}) == [ModelOption("m", efforts=("low",))]
