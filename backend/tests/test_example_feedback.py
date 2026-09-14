from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.claude_cli import ClaudeCli, GenerationError
from app.example_feedback import ExampleCoach
from app.main import create_app
from app.models import ExampleFeedback
from app.store import SessionStore
from tests.test_api import FakeGenerator, InlineExecutor

PROMPT = "Target: {{expression}} ({{meaning}}; {{usage_note}})\nSentence: {{sentence}}"


class FakeCli:
    def __init__(self, output: dict):
        self.output = output
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def run(self, prompt: str, schema: dict, on_event=None) -> dict:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        return {"structured_output": self.output}


@pytest.fixture
def agent_dir(tmp_path) -> Path:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "feedback.md").write_text(PROMPT)
    return tmp_path


def test_prompt_names_the_target_and_the_sentence(agent_dir):
    coach = ExampleCoach(FakeCli({}), agent_dir)
    prompt = coach.build_prompt("off the top of my head", "without checking", "needs 'my'", "I can't say off the top of head.")
    assert prompt == "Target: off the top of my head (without checking; needs 'my')\nSentence: I can't say off the top of head."


def test_feedback_is_the_two_lines_the_model_returns(agent_dir):
    cli = FakeCli({"paraphrase": "I can't say off the top of my head.", "feedback": "You dropped 'my'; the expression needs it."})
    coach = ExampleCoach(cli, agent_dir)
    result = coach.feedback("off the top of my head", "without checking", "", "I can't say off the top of head.")
    assert result == ExampleFeedback(
        paraphrase="I can't say off the top of my head.", feedback="You dropped 'my'; the expression needs it."
    )
    assert cli.schemas[0]["required"] == ["paraphrase", "feedback"]


def test_the_feedback_run_has_no_tools_and_no_mcp():
    cmd = ClaudeCli(model="opus", effort="low", tools=(), mcp_config=None).build_command({"type": "object"})
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--allowedTools" not in cmd
    assert "--mcp-config" not in cmd
    assert "--strict-mcp-config" in cmd


class FakeCoach:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[tuple] = []

    def feedback(self, expression: str, meaning: str, usage_note: str, sentence: str) -> ExampleFeedback:
        self.calls.append((expression, meaning, usage_note, sentence))
        if self.error:
            raise self.error
        return ExampleFeedback(paraphrase=f"{sentence} (native)", feedback="Good.")


def client_with(tmp_path, coach) -> TestClient:
    app = create_app(SessionStore(tmp_path / "s.db"), FakeGenerator(), InlineExecutor(), example_coach=coach)
    return TestClient(app)


def test_feedback_endpoint_returns_paraphrase_and_feedback(tmp_path):
    coach = FakeCoach()
    with client_with(tmp_path, coach) as c:
        res = c.post(
            "/api/example/feedback",
            json={"expression": "rivalry", "meaning": "competition", "usage_note": "noun", "user_text": "The rivalry make them faster."},
        )
        assert res.status_code == 200
        assert res.json() == {"paraphrase": "The rivalry make them faster. (native)", "feedback": "Good."}
        assert coach.calls == [("rivalry", "competition", "noun", "The rivalry make them faster.")]


def test_feedback_endpoint_reports_a_failed_run(tmp_path):
    with client_with(tmp_path, FakeCoach(GenerationError("claude timed out after 90s"))) as c:
        res = c.post("/api/example/feedback", json={"expression": "x", "meaning": "y", "user_text": "z"})
        assert res.status_code == 502
        assert "claude timed out" in res.json()["detail"]


def test_feedback_endpoint_is_off_without_a_coach(tmp_path):
    with client_with(tmp_path, None) as c:
        res = c.post("/api/example/feedback", json={"expression": "x", "meaning": "y", "user_text": "z"})
        assert res.status_code == 503
