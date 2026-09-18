import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import InvalidSetting, Settings, SettingsStore, mask
from app.store import SessionStore
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor


@pytest.fixture
def store(tmp_path):
    return SettingsStore(tmp_path / "s.db")


def test_default_when_neither_env_nor_db(store):
    settings = Settings.resolve({}, store)
    assert settings.get("VOICE_PROVIDER") == "openai"
    assert settings.source("VOICE_PROVIDER") == "default"


def test_env_beats_default_and_blank_env_counts_as_unset(store):
    settings = Settings.resolve({"CLAUDE_MODEL": "sonnet", "TOPICS_MODEL": "  "}, store)
    assert settings.get("CLAUDE_MODEL") == "sonnet"
    assert settings.source("CLAUDE_MODEL") == "env"
    assert settings.get("TOPICS_MODEL") == "sonnet"
    assert settings.source("TOPICS_MODEL") == "default"


def test_db_beats_env(store):
    store.save({"VOICE_PROVIDER": "gemini"})
    settings = Settings.resolve({"VOICE_PROVIDER": "openai"}, store)
    assert settings.voice_provider == "gemini"
    assert settings.source("VOICE_PROVIDER") == "db"


def test_none_clears_the_override(store):
    store.save({"VOICE_PROVIDER": "gemini"})
    store.save({"VOICE_PROVIDER": None})
    assert Settings.resolve({"VOICE_PROVIDER": "openai"}, store).voice_provider == "openai"


def test_rejects_unknown_key_and_bad_choice(store):
    with pytest.raises(InvalidSetting):
        store.save({"NOPE": "x"})
    with pytest.raises(InvalidSetting):
        store.save({"VOICE_PROVIDER": "anthropic"})
    assert store.load() == {}


def test_voice_model_defaults_per_provider(store):
    assert Settings({}, {}).voice_model == "gpt-live-1"
    assert Settings({}, {"VOICE_PROVIDER": "gemini"}).voice_model == "gemini-3.8-live-extended-thinking"
    assert Settings({}, {"VOICE_PROVIDER": "gemini", "VOICE_MODEL": "gemini-3.8-live"}).voice_model == "gemini-3.8-live"


def test_thinking_only_for_extended_thinking_model():
    assert Settings({}, {"VOICE_PROVIDER": "gemini"}).voice_thinking == "low"
    assert Settings({}, {"VOICE_PROVIDER": "gemini", "VOICE_MODEL": "gemini-3.8-live"}).voice_thinking is None
    assert Settings({}, {}).voice_thinking is None


def test_voice_api_key_follows_provider():
    env = {"OPENAI_API_KEY": "sk-openai-1234", "GEMINI_API_KEY": "AIza-gemini-5678"}
    assert Settings(env, {}).voice_api_key == "sk-openai-1234"
    assert Settings(env, {"VOICE_PROVIDER": "gemini"}).voice_api_key == "AIza-gemini-5678"


def test_fields_mask_secrets_and_carry_metadata():
    fields = {f.key: f for f in Settings({"OPENAI_API_KEY": "sk-openai-1234"}, {}).fields()}
    assert fields["OPENAI_API_KEY"].value == "…1234"
    assert fields["OPENAI_API_KEY"].secret is True
    assert fields["GEMINI_API_KEY"].value == ""
    assert fields["CLAUDE_EFFORT"].choices == ("low", "medium", "high", "xhigh", "max")
    assert "gemini-3.8-live" in fields["VOICE_MODEL"].suggestions
    assert fields["VOICE_MODEL"].group == "voice"


def test_claude_skills_split():
    assert Settings({"CLAUDE_SKILLS": "stop-slop, cotidie:write-like-me,"}, {}).claude_skills == (
        "stop-slop",
        "cotidie:write-like-me",
    )


def test_mask():
    assert mask("") == ""
    assert mask("short") == "…"
    assert mask("sk-proj-abcdef1234") == "…1234"


def settings_client(tmp_path, env, rebuild=None):
    store = SessionStore(tmp_path / "s.db")
    app = create_app(store, Services(FakeGenerator()), InlineExecutor(), rebuild=rebuild, env=env)
    return TestClient(app)


def test_get_masks_secrets_and_names_sources(tmp_path):
    with settings_client(tmp_path, {"OPENAI_API_KEY": "sk-openai-1234", "CLAUDE_MODEL": "sonnet"}) as c:
        fields = {f["key"]: f for f in c.get("/api/settings").json()["fields"]}
    assert fields["OPENAI_API_KEY"] == {
        "key": "OPENAI_API_KEY",
        "group": "voice",
        "value": "…1234",
        "source": "env",
        "secret": True,
        "default": "",
        "choices": None,
        "suggestions": [],
    }
    assert fields["CLAUDE_MODEL"]["value"] == "sonnet" and fields["CLAUDE_MODEL"]["source"] == "env"
    assert fields["VOICE_PROVIDER"]["source"] == "default"


def test_put_stores_overrides_and_rebuilds_services(tmp_path):
    seen = []

    def rebuild(settings):
        seen.append(settings.voice_provider)
        return Services(FakeGenerator(), voice_key_name=settings.voice_api_key_name)

    with settings_client(tmp_path, {}, rebuild) as c:
        res = c.put("/api/settings", json={"values": {"VOICE_PROVIDER": "gemini", "GEMINI_API_KEY": "AIza-x-5678"}})
        assert res.status_code == 200
        fields = {f["key"]: f for f in res.json()["fields"]}
        assert fields["VOICE_PROVIDER"] == fields["VOICE_PROVIDER"] | {"value": "gemini", "source": "db"}
        assert fields["GEMINI_API_KEY"]["value"] == "…5678"
        # The live endpoints now name the Gemini key when the provider has none.
        assert "GEMINI_API_KEY" in c.post("/api/phrase/sessions", json={}).json()["detail"]
        # Overrides survive a fresh read.
        assert {f["key"]: f["value"] for f in c.get("/api/settings").json()["fields"]}["VOICE_PROVIDER"] == "gemini"
    assert seen == ["gemini"]


def test_put_rejects_bad_values_without_saving(tmp_path):
    with settings_client(tmp_path, {}) as c:
        assert c.put("/api/settings", json={"values": {"VOICE_PROVIDER": "anthropic"}}).status_code == 400
        assert c.put("/api/settings", json={"values": {"NOPE": "x"}}).status_code == 400
        assert {f["key"]: f["source"] for f in c.get("/api/settings").json()["fields"]}["VOICE_PROVIDER"] == "default"


def test_put_null_clears_an_override(tmp_path):
    with settings_client(tmp_path, {"CLAUDE_EFFORT": "high"}) as c:
        c.put("/api/settings", json={"values": {"CLAUDE_EFFORT": "max"}})
        res = c.put("/api/settings", json={"values": {"CLAUDE_EFFORT": None}})
    field = {f["key"]: f for f in res.json()["fields"]}["CLAUDE_EFFORT"]
    assert field["value"] == "high" and field["source"] == "env"
