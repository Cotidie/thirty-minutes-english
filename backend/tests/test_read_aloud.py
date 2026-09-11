import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.read_aloud import AgentDefinition, LiveSessionError, ReadAloudCoach
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


def make_client(tmp_path, coach):
    app = create_app(SessionStore(tmp_path / "s.db"), FakeGenerator(), InlineExecutor(), coach=coach)
    return TestClient(app)


def test_definition_fills_instructions_and_paragraph(agent_dir):
    session = AgentDefinition(agent_dir).session_for(PARAGRAPH)
    assert session["model"] == "gpt-live-1"
    assert session["instructions"] == "You are Coach.\n"
    assert session["input"][0]["content"][0]["text"] == f"Read:\n\n{PARAGRAPH}"


def test_definition_does_not_mutate_template(agent_dir):
    definition = AgentDefinition(agent_dir)
    definition.session_for("first")
    assert "{{paragraph}}" in definition.session_for("second")["input"][0]["content"][0]["text"].replace("second", "{{paragraph}}")


def test_start_returns_upstream_answer(tmp_path, agent_dir):
    sessions = FakeLiveSessions()
    with make_client(tmp_path, ReadAloudCoach(AgentDefinition(agent_dir), sessions)) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH, "sdp": "v=0 offer"})
    assert res.status_code == 201
    assert res.json() == {"session": {"id": "live_123"}, "transport": {"type": "webrtc", "sdp": "v=0 answer"}}
    session, sdp = sessions.calls[0]
    assert sdp == "v=0 offer"
    assert PARAGRAPH in session["input"][0]["content"][0]["text"]
    assert session["instructions"] == "You are Coach.\n"


def test_503_when_coach_not_configured(tmp_path):
    with make_client(tmp_path, None) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH, "sdp": "v=0"})
    assert res.status_code == 503
    assert "OPENAI_API_KEY" in res.json()["detail"]


def test_upstream_error_becomes_502(tmp_path, agent_dir):
    sessions = FakeLiveSessions(LiveSessionError(401, "Incorrect API key"))
    with make_client(tmp_path, ReadAloudCoach(AgentDefinition(agent_dir), sessions)) as c:
        res = c.post("/api/read-aloud/sessions", json={"paragraph": PARAGRAPH, "sdp": "v=0"})
    assert res.status_code == 502
    assert "Incorrect API key" in res.json()["detail"]


@pytest.mark.parametrize("body", [{"paragraph": "", "sdp": "v=0"}, {"paragraph": PARAGRAPH, "sdp": "  "}])
def test_rejects_blank_fields(tmp_path, agent_dir, body):
    with make_client(tmp_path, ReadAloudCoach(AgentDefinition(agent_dir), FakeLiveSessions())) as c:
        assert c.post("/api/read-aloud/sessions", json=body).status_code == 422
