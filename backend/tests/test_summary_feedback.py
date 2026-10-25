from pathlib import Path

from fastapi.testclient import TestClient

from app.coaching.summary_feedback import SummaryCoach
from app.db import Database
from app.main import create_app
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor

AGENT_DIR = Path(__file__).parents[2] / "agents" / "summary-coach"
PARAGRAPH = "Seoul scrapped its trams in 1968. Now it is laying tracks again."
ANSWER = {
    "missed": [],
    "fixes": [{"said": "was remove", "better": "got rid of"}],
    "summary": "Seoul got rid of its trams in 1968 and is now bringing them back.",
}


class FakeCli:
    def __init__(self):
        self.prompts: list[str] = []

    def run(self, prompt: str, schema: dict, on_message=None) -> dict:
        self.prompts.append(prompt)
        return ANSWER


def test_a_spoken_summary_is_judged_against_its_paragraph_and_kept_with_the_session(tmp_path):
    cli = FakeCli()
    services = Services(FakeGenerator(), summary_coach=SummaryCoach(cli, AGENT_DIR))
    app = create_app(Database(tmp_path / "s.db"), services, InlineExecutor())
    said = "Seoul was remove the tram at 1968 and now making again."
    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={"topic": "X"}).json()["session_id"]
        feedback = c.post("/api/summary/feedback", json={"paragraph": PARAGRAPH, "user_text": said})
        assert feedback.json() == ANSWER
        assert PARAGRAPH in cli.prompts[0] and said in cli.prompts[0] and "{{" not in cli.prompts[0]

        paragraph_id = c.get(f"/api/sessions/{sid}").json()["content"]["article"]["paragraphs"][1]["id"]
        kept = c.post("/api/summaries", json={"paragraph_id": paragraph_id, "user_text": said, "feedback": ANSWER, "seconds": 12})
        assert kept.status_code == 201
        [summary] = c.get(f"/api/summaries?session_id={sid}").json()
        assert (summary["paragraph_id"], summary["user_text"], summary["feedback"]) == (paragraph_id, said, ANSWER)
        assert c.post("/api/summaries", json={"paragraph_id": 999, "user_text": said, "feedback": ANSWER}).status_code == 404

        assert c.post("/api/summary/feedback", json={"paragraph": PARAGRAPH, "user_text": " "}).status_code == 422
        c.delete(f"/api/sessions/{sid}")
        assert c.get(f"/api/summaries?session_id={sid}").json() == []


def test_the_summary_round_is_503_without_a_voice_key(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), InlineExecutor())
    with TestClient(app) as c:
        assert c.post("/api/summary/sessions", json={"paragraph": PARAGRAPH}).status_code == 503
        assert c.post("/api/summary/feedback", json={"paragraph": PARAGRAPH, "user_text": "x"}).status_code == 503
