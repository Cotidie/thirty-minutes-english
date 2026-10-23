import json

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.net import HttpError
from app.voice.live import AgentDefinition, GeminiTranscriber, GeminiVoice, LiveAgent, OpenAIVoice, vocabulary
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor

PARAGRAPH = "Researchers verified that the new battery lasts twice as long."


@pytest.fixture
def agent_dir(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "live.md").write_text("You are Coach.\n")
    (tmp_path / "session.json").write_text(
        json.dumps(
            {
                "model": "gpt-live-1",
                "instructions": "<contents of prompts/live.md>",
                "input": [
                    {
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "Read:\n\n{{paragraph}}"}],
                    }
                ],
            }
        )
    )
    return tmp_path


class FakeLiveSessions:
    """A provider that records the OpenAI-shaped session it would have sent."""

    name = "fake"

    def __init__(self, error: HttpError | None = None):
        self.calls: list[tuple[dict, str | None]] = []
        self.error = error

    def open(self, definition: AgentDefinition, sdp: str | None, **values: str) -> dict:
        self.calls.append((definition.session_for(**values), sdp))
        if self.error:
            raise self.error
        return {"provider": "openai", "session": {"id": "live_123"}, "transport": {"type": "webrtc", "sdp": "v=0 answer"}}


def make_client(tmp_path, agents, transcriber=None):
    services = Services(FakeGenerator(), agents=agents, transcriber=transcriber)
    return TestClient(create_app(Database(tmp_path / "s.db"), services, InlineExecutor()))


def read_aloud(agent_dir, sessions=None):
    return {"read-aloud": LiveAgent("read-aloud", AgentDefinition(agent_dir), sessions or FakeLiveSessions())}


def test_definition_fills_instructions_and_placeholders(agent_dir):
    session = AgentDefinition(agent_dir).session_for(paragraph=PARAGRAPH)
    assert session["model"] == "gpt-live-1"
    assert session["instructions"] == "You are Coach.\n"
    assert session["input"][0]["content"][0]["text"] == f"Read:\n\n{PARAGRAPH}"


def test_definition_does_not_mutate_template(agent_dir):
    definition = AgentDefinition(agent_dir)
    definition.session_for(paragraph="first")
    assert definition.session_for(paragraph="second")["input"][0]["content"][0]["text"] == "Read:\n\nsecond"


def test_definition_leaves_unknown_placeholders_alone(agent_dir):
    session = AgentDefinition(agent_dir).session_for(topic="unrelated")
    assert session["input"][0]["content"][0]["text"] == "Read:\n\n{{paragraph}}"


def test_start_returns_upstream_answer(tmp_path, agent_dir):
    sessions = FakeLiveSessions()
    with make_client(tmp_path, read_aloud(agent_dir, sessions)) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH, "sdp": "v=0 offer"})
    assert res.status_code == 201
    assert res.json() == {
        "provider": "openai",
        "session": {"id": "live_123"},
        "transport": {"type": "webrtc", "sdp": "v=0 answer"},
    }
    session, sdp = sessions.calls[0]
    assert sdp == "v=0 offer"
    assert PARAGRAPH in session["input"][0]["content"][0]["text"]
    assert session["instructions"] == "You are Coach.\n"


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/read-aloud/sessions", {"paragraph": PARAGRAPH, "sdp": "v=0"}),
        ("/api/example/sessions", {"sdp": "v=0", "expression": "x", "meaning": "y"}),
    ],
)
def test_503_when_agent_not_configured(tmp_path, path, body):
    with make_client(tmp_path, {}) as c:
        res = c.post(path, json=body)
    assert res.status_code == 503
    assert "OPENAI_API_KEY" in res.json()["detail"]


def test_upstream_error_becomes_502(tmp_path, agent_dir):
    sessions = FakeLiveSessions(HttpError(401, "Incorrect API key"))
    with make_client(tmp_path, read_aloud(agent_dir, sessions)) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH, "sdp": "v=0"})
    assert res.status_code == 502
    assert "Incorrect API key" in res.json()["detail"]


def test_rejects_blank_paragraph(tmp_path, agent_dir):
    with make_client(tmp_path, read_aloud(agent_dir)) as c:
        assert c.post("/api/read-aloud/sessions", json={"paragraph": "", "sdp": "v=0"}).status_code == 422


def test_openai_provider_needs_an_offer_and_overrides_the_model(agent_dir, http):
    http.json = {"session": {"id": "live_1"}, "transport": {"type": "webrtc", "sdp": "v=0 answer"}}
    voice = OpenAIVoice("sk-test", "gpt-live-2")
    with pytest.raises(HttpError) as e:
        voice.open(AgentDefinition(agent_dir), None, paragraph=PARAGRAPH)
    assert e.value.status == 400

    answer = voice.open(AgentDefinition(agent_dir), "v=0 offer", paragraph=PARAGRAPH)
    assert answer["provider"] == "openai" and answer["transport"]["sdp"] == "v=0 answer"
    sent = http.sent()
    assert sent["session"]["model"] == "gpt-live-2"
    assert sent["transport"] == {"type": "webrtc", "sdp": "v=0 offer"}
    assert http.requests[0].headers["Authorization"] == "Bearer sk-test"


def test_gemini_setup_folds_context_into_the_system_instruction(agent_dir):
    setup = AgentDefinition(agent_dir).gemini_setup("gemini-3.8-live", "Kore", None, paragraph=PARAGRAPH)
    assert setup["model"] == "models/gemini-3.8-live"
    assert setup["systemInstruction"]["parts"][0]["text"] == f"You are Coach.\n\nRead:\n\n{PARAGRAPH}"
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert "thinkingConfig" not in setup["generationConfig"]
    assert setup["inputAudioTranscription"] == {"languageCodes": ["en-US", "ko-KR"]}
    assert setup["outputAudioTranscription"] == {}


def test_gemini_setup_carries_the_thinking_level_when_given(agent_dir):
    setup = AgentDefinition(agent_dir).gemini_setup("gemini-3.8-live-extended-thinking", "Kore", "medium")
    assert setup["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "medium"}


def test_gemini_provider_mints_a_locked_token_and_returns_the_setup(agent_dir, http):
    http.json = {"name": "auth_tokens/abc"}
    voice = GeminiVoice("AIza-test", "gemini-3.8-live-extended-thinking", "Puck", "low")
    answer = voice.open(AgentDefinition(agent_dir), None, paragraph=PARAGRAPH)
    assert answer["provider"] == "gemini"

    sent = http.sent()
    assert sent["uses"] == 1
    assert sent["bidiGenerateContentSetup"]["model"] == "models/gemini-3.8-live-extended-thinking"
    assert sent["bidiGenerateContentSetup"] == answer["setup"]
    assert sent["expireTime"].endswith("Z") and sent["newSessionExpireTime"].endswith("Z")
    assert http.requests[0].headers["x-goog-api-key"] == "AIza-test"
    assert answer["provider"] == "gemini"
    assert answer["url"].endswith("BidiGenerateContentConstrained?access_token=auth_tokens/abc")
    assert answer["setup"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert PARAGRAPH in answer["setup"]["systemInstruction"]["parts"][0]["text"]


def test_gemini_round_needs_no_offer(tmp_path, agent_dir, http):
    http.json = {"name": "auth_tokens/abc"}
    voice = GeminiVoice("AIza-test", "gemini-3.8-live", "Kore", None)
    agents = {"read-aloud": LiveAgent("read-aloud", AgentDefinition(agent_dir), voice)}
    with make_client(tmp_path, agents) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH})
    assert res.status_code == 201
    assert res.json()["provider"] == "gemini"
    assert "setup" in res.json() and "url" in res.json()


def test_transcriber_hears_only_english_or_korean_primed_with_the_paragraph_words(http):
    http.json = {"name": "auth_tokens/abc"}
    answer = GeminiTranscriber("AIza-test").start(PARAGRAPH)
    setup = http.sent()["bidiGenerateContentSetup"]
    assert setup == {
        "model": "models/gemini-3.5-transcribe-live",
        "generationConfig": {"responseModalities": ["TEXT"]},
        "inputAudioTranscription": {
            "languageCodes": ["en-US", "ko-KR"],
            "customVocabulary": ["Researchers", "verified", "that", "battery", "lasts", "twice", "long"],
        },
    }
    assert answer["provider"] == "gemini" and answer["setup"] == setup
    assert answer["url"].endswith("?access_token=auth_tokens/abc")


def test_vocabulary_keeps_each_term_once_and_drops_short_common_words():
    text = "I think AI at MIT and Segev's team found the cortical neuron. Cortical again, at five-to-eight layers."
    assert vocabulary(text) == ["think", "AI", "MIT", "Segev's", "team", "found", "cortical", "neuron", "again", "five-to-eight", "layers"]
    assert len(vocabulary(" ".join(f"word{chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(300)))) == 100


def test_summary_round_opens_the_transcriber_on_the_paragraph(tmp_path, http):
    http.json = {"name": "auth_tokens/abc"}
    with make_client(tmp_path, {}, GeminiTranscriber("AIza-test")) as c:
        res = c.post("/api/summary/sessions", json={"paragraph": PARAGRAPH})
        assert c.post("/api/summary/sessions", json={"paragraph": " "}).status_code == 422
    assert res.status_code == 201
    assert res.json()["provider"] == "gemini"
    assert "battery" in http.sent()["bidiGenerateContentSetup"]["inputAudioTranscription"]["customVocabulary"]


def test_summary_round_is_off_without_the_gemini_key(tmp_path):
    with make_client(tmp_path, {}) as c:
        res = c.post("/api/summary/sessions", json={"paragraph": PARAGRAPH})
    assert res.status_code == 503
    assert "GEMINI_API_KEY" in res.json()["detail"]


@pytest.fixture
def example_agent_dir(tmp_path):
    directory = tmp_path / "example"
    (directory / "prompts").mkdir(parents=True)
    (directory / "prompts" / "live.md").write_text("You are Echo.\n")
    (directory / "session.json").write_text(
        json.dumps(
            {
                "model": "gpt-live-1",
                "instructions": "<contents of prompts/live.md>",
                "input": [
                    {
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "{{expression}} / {{meaning}} / {{usage_note}}"}],
                    }
                ],
            }
        )
    )
    return directory


def test_example_session_carries_the_expression(tmp_path, example_agent_dir):
    sessions = FakeLiveSessions()
    agents = {"example": LiveAgent("example", AgentDefinition(example_agent_dir), sessions)}
    with make_client(tmp_path, agents) as c:
        res = c.post(
            "/api/example/sessions",
            json={"sdp": "v=0 offer", "expression": "read too much into", "meaning": "find a meaning that is not there"},
        )
    assert res.status_code == 201
    session, sdp = sessions.calls[0]
    assert sdp == "v=0 offer"
    assert session["input"][0]["content"][0]["text"] == "read too much into / find a meaning that is not there / none"
    assert session["instructions"] == "You are Echo.\n"
