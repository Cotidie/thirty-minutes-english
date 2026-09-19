import io
import json
import urllib.error

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
    assert Settings.resolve({}, store).get("VOICE_PROVIDER") == "openai"


def test_env_beats_default_and_blank_env_counts_as_unset(store):
    settings = Settings.resolve({"CLAUDE_MODEL": "sonnet", "TOPICS_MODEL": "  "}, store)
    assert settings.get("CLAUDE_MODEL") == "sonnet"
    assert settings.get("TOPICS_MODEL") == "sonnet"


def test_saved_beats_env(store):
    store.save({"VOICE_PROVIDER": "gemini"})
    assert Settings.resolve({"VOICE_PROVIDER": "openai"}, store).voice_provider == "gemini"


def test_rejects_unknown_key_and_bad_choice(store):
    with pytest.raises(InvalidSetting):
        store.save({"NOPE": "x"})
    with pytest.raises(InvalidSetting):
        store.save({"VOICE_PROVIDER": "anthropic"})
    with pytest.raises(InvalidSetting):
        store.save({"VOICE_NAME": "Siri"})
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
    assert "Kore" in fields["VOICE_NAME"].choices and len(fields["VOICE_NAME"].choices) == 30
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


def test_get_masks_secrets(tmp_path):
    with settings_client(tmp_path, {"OPENAI_API_KEY": "sk-openai-1234", "CLAUDE_MODEL": "sonnet"}) as c:
        fields = {f["key"]: f for f in c.get("/api/settings").json()["fields"]}
    assert fields["OPENAI_API_KEY"] == {
        "key": "OPENAI_API_KEY",
        "group": "keys",
        "value": "…1234",
        "secret": True,
        "default": "",
        "choices": None,
        "suggestions": [],
        "labels": {},
    }
    assert fields["CLAUDE_MODEL"]["value"] == "sonnet"
    assert fields["VOICE_NAME"]["choices"][:2] == ["Zephyr", "Puck"]
    assert fields["VOICE_NAME"]["labels"]["Kore"] == "Firm"


def test_put_stores_overrides_and_rebuilds_services(tmp_path):
    seen = []

    def rebuild(settings):
        seen.append(settings.voice_provider)
        return Services(FakeGenerator(), voice_key_name=settings.voice_api_key_name)

    with settings_client(tmp_path, {}, rebuild) as c:
        res = c.put("/api/settings", json={"values": {"VOICE_PROVIDER": "gemini", "GEMINI_API_KEY": "AIza-x-5678"}})
        assert res.status_code == 200
        fields = {f["key"]: f for f in res.json()["fields"]}
        assert fields["VOICE_PROVIDER"]["value"] == "gemini"
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
        assert {f["key"]: f["value"] for f in c.get("/api/settings").json()["fields"]}["VOICE_PROVIDER"] == "openai"


class FakeGet:
    """urlopen stand-in: records the request, answers 200 or raises the given HTTP error."""

    def __init__(self, status: int = 200, message: str = ""):
        self.status = status
        self.message = message
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        if self.status != 200:
            body = io.BytesIO(json.dumps({"error": {"message": self.message}}).encode())
            raise urllib.error.HTTPError(req.full_url, self.status, "err", {}, body)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_key_test_uses_the_typed_value_with_the_provider_header(tmp_path, monkeypatch):
    get = FakeGet()
    monkeypatch.setattr("app.keycheck.urllib.request.urlopen", get)
    with settings_client(tmp_path, {}) as c:
        res = c.post("/api/settings/test-key", json={"key": "GEMINI_API_KEY", "value": "AIza-typed"})
    assert res.json() == {"ok": True, "message": "key works"}
    assert get.requests[0].get_header("X-goog-api-key") == "AIza-typed"
    assert "generativelanguage" in get.requests[0].full_url


def test_key_test_falls_back_to_the_saved_key_and_reports_failures(tmp_path, monkeypatch):
    get = FakeGet(401, "Incorrect API key provided")
    monkeypatch.setattr("app.keycheck.urllib.request.urlopen", get)
    with settings_client(tmp_path, {"OPENAI_API_KEY": "sk-saved"}) as c:
        res = c.post("/api/settings/test-key", json={"key": "OPENAI_API_KEY"})
    assert res.json() == {"ok": False, "message": "401: Incorrect API key provided"}
    assert get.requests[0].get_header("Authorization") == "Bearer sk-saved"


def test_key_test_without_any_key(tmp_path):
    with settings_client(tmp_path, {}) as c:
        assert c.post("/api/settings/test-key", json={"key": "GEMINI_API_KEY"}).json()["ok"] is False
        assert c.post("/api/settings/test-key", json={"key": "NOPE"}).status_code == 422
