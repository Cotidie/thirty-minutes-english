import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.live import AgentDefinition, LiveAgent, LiveSessionError
from app.store import SessionStore
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
    def __init__(self, error: LiveSessionError | None = None):
        self.calls: list[tuple[dict, str]] = []
        self.error = error

    def create(self, session: dict, sdp: str) -> dict:
        self.calls.append((session, sdp))
        if self.error:
            raise self.error
        return {"session": {"id": "live_123"}, "transport": {"type": "webrtc", "sdp": "v=0 answer"}}


def make_client(tmp_path, agents):
    app = create_app(SessionStore(tmp_path / "s.db"), FakeGenerator(), InlineExecutor(), agents=agents)
    return TestClient(app)


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
    assert res.json() == {"session": {"id": "live_123"}, "transport": {"type": "webrtc", "sdp": "v=0 answer"}}
    session, sdp = sessions.calls[0]
    assert sdp == "v=0 offer"
    assert PARAGRAPH in session["input"][0]["content"][0]["text"]
    assert session["instructions"] == "You are Coach.\n"


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/read-aloud/sessions", {"paragraph": PARAGRAPH, "sdp": "v=0"}),
        ("/api/phrase/sessions", {"sdp": "v=0"}),
        ("/api/example/sessions", {"sdp": "v=0", "expression": "x", "meaning": "y"}),
    ],
)
def test_503_when_agent_not_configured(tmp_path, path, body):
    with make_client(tmp_path, {}) as c:
        res = c.post(path, json=body)
    assert res.status_code == 503
    assert "OPENAI_API_KEY" in res.json()["detail"]


def test_upstream_error_becomes_502(tmp_path, agent_dir):
    sessions = FakeLiveSessions(LiveSessionError(401, "Incorrect API key"))
    with make_client(tmp_path, read_aloud(agent_dir, sessions)) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH, "sdp": "v=0"})
    assert res.status_code == 502
    assert "Incorrect API key" in res.json()["detail"]


@pytest.mark.parametrize("body", [{"paragraph": "", "sdp": "v=0"}, {"paragraph": PARAGRAPH, "sdp": "  "}])
def test_rejects_blank_fields(tmp_path, agent_dir, body):
    with make_client(tmp_path, read_aloud(agent_dir)) as c:
        assert c.post("/api/read-aloud/sessions", json=body).status_code == 422


@pytest.fixture
def phrase_agent_dir(tmp_path):
    directory = tmp_path / "phrase"
    (directory / "prompts").mkdir(parents=True)
    (directory / "prompts" / "live.md").write_text("You are Phrase.\n")
    (directory / "session.json").write_text(
        json.dumps(
            {
                "model": "gpt-live-1",
                "instructions": "<contents of prompts/live.md>",
                "input": [
                    {
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "Topic: {{topic}}"}],
                    }
                ],
            }
        )
    )
    return directory


def phrase(agent_dir, sessions=None):
    return {"phrase": LiveAgent("phrase", AgentDefinition(agent_dir), sessions or FakeLiveSessions())}


def test_phrase_session_carries_the_topic(tmp_path, phrase_agent_dir):
    sessions = FakeLiveSessions()
    with make_client(tmp_path, phrase(phrase_agent_dir, sessions)) as c:
        res = c.post("/api/phrase/sessions", json={"sdp": "v=0 offer", "topic": "Digital twins"})
    assert res.status_code == 201
    session, sdp = sessions.calls[0]
    assert sdp == "v=0 offer"
    assert session["input"][0]["content"][0]["text"] == "Topic: Digital twins"
    assert session["instructions"] == "You are Phrase.\n"


def test_phrase_session_without_a_topic_still_starts(tmp_path, phrase_agent_dir):
    sessions = FakeLiveSessions()
    with make_client(tmp_path, phrase(phrase_agent_dir, sessions)) as c:
        assert c.post("/api/phrase/sessions", json={"sdp": "v=0 offer"}).status_code == 201
    assert "{{topic}}" not in sessions.calls[0][0]["input"][0]["content"][0]["text"]


def test_agents_are_independent(tmp_path, agent_dir, phrase_agent_dir):
    agents = read_aloud(agent_dir) | phrase(phrase_agent_dir)
    with make_client(tmp_path, agents) as c:
        assert c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH, "sdp": "v=0"}).status_code == 201
        assert c.post("/api/phrase/sessions", json={"sdp": "v=0"}).status_code == 201


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
