from pathlib import Path

import pytest
from tests.conftest import admin_client

from app.db import Database
from app.main import create_app
from app.net import HttpError
from app.voice.live import AgentDefinition, GeminiTranscriber, GeminiVoice, LiveAgent, vocabulary
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor

PARAGRAPH = "Researchers verified that the new battery lasts twice as long."
SUMMARY_DIR = Path(__file__).parents[2] / "agents" / "summary-coach"


def coach_dir(directory: Path, instructions: str, context: str) -> Path:
    (directory / "prompts").mkdir(parents=True)
    (directory / "prompts" / "live.md").write_text(instructions)
    (directory / "prompts" / "context.md").write_text(context)
    return directory


@pytest.fixture
def agent_dir(tmp_path):
    return coach_dir(tmp_path, "You are Coach.\n", "Read:\n\n{{paragraph}}\n")


def instruction_of(setup: dict) -> str:
    return setup["systemInstruction"]["parts"][0]["text"]


class FakeVoice:
    """A Gemini voice that records the system instruction it would have sent."""

    model = "fake"

    def __init__(self, error: HttpError | None = None):
        self.instructions: list[str] = []
        self.error = error

    def open(self, definition: AgentDefinition, **values: str) -> dict:
        self.instructions.append(instruction_of(definition.gemini_setup("m", "Kore", None, **values)))
        if self.error:
            raise self.error
        return {"url": "wss://live?access_token=t", "setup": {"model": "models/m"}}


def make_client(tmp_path, agents, transcriber=None):
    services = Services(FakeGenerator(), agents=agents, transcriber=transcriber)
    return admin_client(create_app(Database(tmp_path / "s.db"), services, InlineExecutor()))


def read_aloud(agent_dir, voice=None):
    return {"read-aloud": LiveAgent("read-aloud", AgentDefinition(agent_dir), voice or FakeVoice())}


def test_definition_leaves_unknown_placeholders_alone(agent_dir):
    setup = AgentDefinition(agent_dir).gemini_setup("m", "Kore", None, topic="unrelated")
    assert instruction_of(setup) == "You are Coach.\n\nRead:\n\n{{paragraph}}"


def test_start_returns_upstream_answer(tmp_path, agent_dir):
    voice = FakeVoice()
    with make_client(tmp_path, read_aloud(agent_dir, voice)) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH})
    assert res.status_code == 201
    assert res.json() == {"url": "wss://live?access_token=t", "setup": {"model": "models/m"}}
    assert voice.instructions == [f"You are Coach.\n\nRead:\n\n{PARAGRAPH}"]


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/read-aloud/sessions", {"paragraph": PARAGRAPH}),
        ("/api/example/sessions", {"word": "x", "meaning": "y", "pos": "noun"}),
    ],
)
def test_503_when_agent_not_configured(tmp_path, path, body):
    with make_client(tmp_path, {}) as c:
        res = c.post(path, json=body)
    assert res.status_code == 503
    assert "GEMINI_API_KEY" in res.json()["detail"]


def test_upstream_error_becomes_502(tmp_path, agent_dir):
    voice = FakeVoice(HttpError(401, "API key not valid"))
    with make_client(tmp_path, read_aloud(agent_dir, voice)) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH})
    assert res.status_code == 502
    assert "API key not valid" in res.json()["detail"]


def test_rejects_blank_paragraph(tmp_path, agent_dir):
    with make_client(tmp_path, read_aloud(agent_dir)) as c:
        assert c.post("/api/read-aloud/sessions", json={"paragraph": ""}).status_code == 422


def test_gemini_setup_folds_context_into_the_system_instruction(agent_dir):
    setup = AgentDefinition(agent_dir).gemini_setup("gemini-3.8-live", "Kore", None, paragraph=PARAGRAPH)
    assert setup["model"] == "models/gemini-3.8-live"
    assert instruction_of(setup) == f"You are Coach.\n\nRead:\n\n{PARAGRAPH}"
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
    answer = voice.open(AgentDefinition(agent_dir), paragraph=PARAGRAPH)

    sent = http.sent()
    assert sent["uses"] == 1
    assert sent["bidiGenerateContentSetup"]["model"] == "models/gemini-3.8-live-extended-thinking"
    assert sent["bidiGenerateContentSetup"] == answer["setup"]
    assert sent["expireTime"].endswith("Z") and sent["newSessionExpireTime"].endswith("Z")
    assert http.requests[0].headers["x-goog-api-key"] == "AIza-test"
    assert answer["url"].endswith("BidiGenerateContentConstrained?access_token=auth_tokens/abc")
    assert answer["setup"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert PARAGRAPH in answer["setup"]["systemInstruction"]["parts"][0]["text"]


def test_a_read_aloud_round_opens_on_gemini(tmp_path, agent_dir, http):
    http.json = {"name": "auth_tokens/abc"}
    voice = GeminiVoice("AIza-test", "gemini-3.8-live", "Kore", None)
    agents = {"read-aloud": LiveAgent("read-aloud", AgentDefinition(agent_dir), voice)}
    with make_client(tmp_path, agents) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH})
    assert res.status_code == 201
    assert res.json()["url"].endswith("?access_token=auth_tokens/abc")
    assert res.json()["setup"]["model"] == "models/gemini-3.8-live"


def test_transcriber_hears_only_english_or_korean_primed_with_the_paragraph_words(http):
    http.json = {"name": "auth_tokens/abc"}
    answer = GeminiTranscriber("AIza-test", SUMMARY_DIR).start(PARAGRAPH)
    setup = http.sent()["bidiGenerateContentSetup"]
    assert setup == {
        "model": "models/gemini-3.5-transcribe-live",
        "generationConfig": {"responseModalities": ["TEXT"]},
        "inputAudioTranscription": {
            "languageCodes": ["en-US", "ko-KR"],
            "customVocabulary": ["Researchers", "verified", "that", "battery", "lasts", "twice", "long"],
        },
    }
    assert answer["setup"] == setup
    assert answer["url"].endswith("?access_token=auth_tokens/abc")


def test_vocabulary_keeps_each_term_once_and_drops_short_common_words():
    text = "I think AI at MIT and Segev's team found the cortical neuron. Cortical again, at five-to-eight layers."
    assert vocabulary(text) == ["think", "AI", "MIT", "Segev's", "team", "found", "cortical", "neuron", "again", "five-to-eight", "layers"]
    assert len(vocabulary(" ".join(f"word{chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(300)))) == 100


def test_summary_round_opens_the_transcriber_on_the_paragraph(tmp_path, http):
    http.json = {"name": "auth_tokens/abc"}
    with make_client(tmp_path, {}, GeminiTranscriber("AIza-test", SUMMARY_DIR)) as c:
        res = c.post("/api/summary/sessions", json={"paragraph": PARAGRAPH})
        assert c.post("/api/summary/sessions", json={"paragraph": " "}).status_code == 422
    assert res.status_code == 201
    assert "battery" in http.sent()["bidiGenerateContentSetup"]["inputAudioTranscription"]["customVocabulary"]


def test_summary_round_is_off_without_the_gemini_key(tmp_path):
    with make_client(tmp_path, {}) as c:
        res = c.post("/api/summary/sessions", json={"paragraph": PARAGRAPH})
    assert res.status_code == 503
    assert "GEMINI_API_KEY" in res.json()["detail"]


@pytest.fixture
def example_agent_dir(tmp_path):
    return coach_dir(tmp_path / "example", "You are Echo.\n", "{{word}} / {{meaning}} / {{pos}}\n")


def test_example_session_carries_the_word(tmp_path, example_agent_dir):
    voice = FakeVoice()
    agents = {"example": LiveAgent("example", AgentDefinition(example_agent_dir), voice)}
    with make_client(tmp_path, agents) as c:
        res = c.post("/api/example/sessions", json={"word": "bottleneck", "meaning": "the slowest point", "pos": "noun"})
    assert res.status_code == 201
    assert voice.instructions == ["You are Echo.\n\nbottleneck / the slowest point / noun"]
