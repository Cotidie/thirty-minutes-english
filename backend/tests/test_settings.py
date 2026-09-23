
import pytest
from fastapi.testclient import TestClient

from app.config.settings import InvalidSetting, Settings
from app.config.skills import host_skills
from app.db import Database
from app.main import create_app
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor


@pytest.fixture
def store(tmp_path):
    return Database(tmp_path / "s.db")


def test_default_when_neither_env_nor_db(store):
    assert Settings({}, store.settings.load()).get("VOICE_PROVIDER") == "openai"


def test_env_beats_default_and_blank_env_counts_as_unset(store):
    settings = Settings({"CLAUDE_MODEL": "sonnet", "TOPICS_MODEL": "  "}, store.settings.load())
    assert settings.get("CLAUDE_MODEL") == "sonnet"
    assert settings.get("TOPICS_MODEL") == "sonnet"


def test_saved_beats_env(store):
    store.settings.save({"VOICE_PROVIDER": "gemini"})
    assert Settings({"VOICE_PROVIDER": "openai"}, store.settings.load()).get("VOICE_PROVIDER") == "gemini"


def test_rejects_unknown_key_and_bad_choice(store):
    with pytest.raises(InvalidSetting):
        store.settings.save({"NOPE": "x"})
    with pytest.raises(InvalidSetting):
        store.settings.save({"VOICE_PROVIDER": "anthropic"})
    with pytest.raises(InvalidSetting):
        store.settings.save({"VOICE_NAME": "Siri"})
    assert store.settings.load() == {}


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


def test_claude_skills_split():
    assert Settings({"CLAUDE_SKILLS": "stop-slop, cotidie:write-like-me,"}, {}).claude_skills == (
        "stop-slop",
        "cotidie:write-like-me",
    )


def settings_client(tmp_path, env, rebuild=None):
    store = Database(tmp_path / "s.db")
    app = create_app(store, Services(FakeGenerator()), InlineExecutor(), rebuild=rebuild, env=env)
    return TestClient(app)


def test_get_masks_secrets_and_carries_the_rules_the_modal_applies(tmp_path):
    with settings_client(tmp_path, {"OPENAI_API_KEY": "sk-openai-1234", "CLAUDE_MODEL": "sonnet"}) as c:
        view = c.get("/api/settings").json()
    fields = {f["key"]: f for f in view["fields"]}
    assert fields["OPENAI_API_KEY"]["value"] == "…1234" and fields["OPENAI_API_KEY"]["testable"] is True
    assert fields["CLAUDE_MODEL"]["value"] == "sonnet" and fields["CLAUDE_MODEL"]["testable"] is False
    model = fields["VOICE_MODEL"]
    assert model["follows"] == "VOICE_PROVIDER" and model["free"] is True
    gemini = model["variants"]["gemini"]
    assert [o["id"] for o in gemini["options"]] == [gemini["default"]]  # nothing fetched yet: the default alone
    assert fields["CLAUDE_EFFORT"]["effort_of"] == "CLAUDE_MODEL"
    assert [o["id"] for o in fields["VOICE_PROVIDER"]["options"]] == ["openai", "gemini"] and not fields["VOICE_PROVIDER"]["free"]
    assert fields["VOICE_NAME"]["shown_when"] == ["VOICE_PROVIDER", "gemini"]
    assert fields["COMFY_API_KEY"]["used_when"] == ["IMAGE_PROVIDER", "comfy"]
    assert fields["OPENAI_API_KEY"]["used_when"] is None
    assert all(f["help"] for f in view["fields"])  # every setting explains itself in the modal
    assert {f["group"] for f in view["fields"]} == {g["id"] for g in view["groups"]}


def test_put_stores_overrides_and_rebuilds_services(tmp_path):
    seen = []

    def rebuild(settings):
        seen.append(settings.get("VOICE_PROVIDER"))
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


def test_key_test_uses_the_typed_value_with_the_provider_header(tmp_path, http):
    with settings_client(tmp_path, {}) as c:
        res = c.post("/api/settings/test-key", json={"key": "GEMINI_API_KEY", "value": "AIza-typed"})
    assert res.json() == {"ok": True, "message": "key works"}
    assert http.requests[0].headers["x-goog-api-key"] == "AIza-typed"
    assert http.requests[0].url.host == "generativelanguage.googleapis.com"


def test_key_test_falls_back_to_the_saved_key_and_reports_failures(tmp_path, http):
    http.status, http.json = 401, {"error": {"message": "Incorrect API key provided"}}
    with settings_client(tmp_path, {"OPENROUTER_API_KEY": "sk-saved"}) as c:
        res = c.post("/api/settings/test-key", json={"key": "OPENROUTER_API_KEY"})
    assert res.json() == {"ok": False, "message": "401: Incorrect API key provided"}
    assert http.requests[0].headers["Authorization"] == "Bearer sk-saved"


def test_key_test_without_any_key(tmp_path):
    with settings_client(tmp_path, {}) as c:
        assert c.post("/api/settings/test-key", json={"key": "GEMINI_API_KEY"}).json()["ok"] is False
        assert c.post("/api/settings/test-key", json={"key": "NOPE"}).status_code == 422


def test_threshold_settings_reject_non_numbers(store):
    with pytest.raises(InvalidSetting):
        store.settings.save({"ASSESS_WORD_SCORE": "sixty"})
    with pytest.raises(InvalidSetting):
        store.settings.save({"ASSESS_BREAK_CONFIDENCE": "1.5"})


def test_key_test_for_azure_needs_a_region():
    from app.config.keycheck import check_key

    assert check_key("AZURE_SPEECH_KEY", "az-typed", region=" ").message == "set AZURE_SPEECH_REGION first"


def skill(root, folder: str, head: str) -> None:
    (root / folder).mkdir(parents=True)
    (root / folder / "SKILL.md").write_text(f"---\n{head}\n---\n\n# Body\n")


def test_host_skills_read_name_and_description_from_the_frontmatter(tmp_path):
    skill(tmp_path, "stop-slop", "name: stop-slop\ndescription: Remove AI writing patterns.")
    skill(tmp_path, "humanizer", "name: humanizer\ndescription: |\n  Remove signs\n  of AI writing.")
    (tmp_path / "broken").mkdir()  # no SKILL.md: a broken symlink looks like this
    assert host_skills(tmp_path) == {"humanizer": "Remove signs of AI writing.", "stop-slop": "Remove AI writing patterns."}
    assert host_skills(tmp_path / "missing") == {}


def test_skills_are_ticked_from_the_host_list_and_unknown_names_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.settings.host_skills", lambda: {"stop-slop": "Remove AI writing patterns."})
    with settings_client(tmp_path, {"CLAUDE_SKILLS": "gone-skill"}) as c:
        field = {f["key"]: f for f in c.get("/api/settings").json()["fields"]}["CLAUDE_SKILLS"]
        assert field["multi"] is True
        assert [o["id"] for o in field["options"]] == ["stop-slop", "gone-skill"]
        assert field["options"][0]["description"] == "Remove AI writing patterns."
        assert "Not found" in field["options"][1]["description"]

        refused = c.put("/api/settings", json={"values": {"CLAUDE_SKILLS": "stop-slop,typo-skill"}})
        assert refused.status_code == 400 and "typo-skill" in refused.json()["detail"]
        assert c.put("/api/settings", json={"values": {"CLAUDE_SKILLS": "stop-slop"}}).status_code == 200
