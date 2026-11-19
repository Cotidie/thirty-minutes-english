import sqlite3
from pathlib import Path

from app.coaching.summary_feedback import SummaryCoach
from app.coaching.summary_judging import NOT_SAVED, RESTARTED, SummaryJudges
from app.db import Database
from app.live.changes import SessionChange
from app.llm import GenerationError
from app.main import create_app
from app.wiring import Services
from tests.conftest import Recorder, add_user, admin_client, sample_draft
from tests.test_api import FakeGenerator, HeldExecutor, InlineExecutor

AGENT_DIR = Path(__file__).parents[2] / "agents" / "summary-coach"
PARAGRAPH = "Seoul scrapped its trams in 1968. Now it is laying tracks again."
ANSWER = {
    "missed": [],
    "fixes": [{"said": "was remove", "better": "got rid of"}],
    "summary": "Seoul got rid of its trams in 1968 and is now bringing them back.",
}
SAID = "Seoul was remove the tram at 1968 and now making again."
AGAIN = "Only a summary whose feedback failed can be judged again."
NOT_REMOVED = "Only a summary whose feedback failed can be removed."


class FakeCli:
    def __init__(self):
        self.prompts: list[str] = []

    def run(self, prompt: str, schema: dict, on_message=None) -> dict:
        self.prompts.append(prompt)
        return ANSWER


class Down:
    def feedback(self, paragraph, user_text):
        raise GenerationError("down")


def judging_app(tmp_path, coach, judges):
    db = Database(tmp_path / "s.db")
    return db, create_app(db, Services(FakeGenerator(), summary_coach=coach), InlineExecutor(), judges=judges)


def a_paragraph(client) -> tuple[int, dict]:
    sid = client.post("/api/sessions", json={"topic": "X"}).json()["session_id"]
    return sid, client.get(f"/api/sessions/{sid}").json()["content"]["article"]["paragraphs"][1]


def test_a_spoken_summary_is_judged_on_the_server_and_kept_with_who_said_it(tmp_path):
    cli = FakeCli()
    db, app = judging_app(tmp_path, SummaryCoach(cli, AGENT_DIR), InlineExecutor())
    with admin_client(app) as c:
        sid, paragraph = a_paragraph(c)
        kept = c.post("/api/summaries", json={"paragraph_id": paragraph["id"], "user_text": SAID, "seconds": 12})
        assert kept.status_code == 201
        summary = kept.json()
        admin = db.accounts.by_email("admin@example.com")
        assert (summary["status"], summary["feedback"], summary["error"]) == ("done", ANSWER, None)
        assert (summary["speaker"], summary["mine"], summary["seconds"]) == (admin.username, True, 12)
        assert paragraph["text"] in cli.prompts[0] and SAID in cli.prompts[0] and "{{" not in cli.prompts[0]
        assert c.get(f"/api/summaries?session_id={sid}").json() == [summary]

        assert c.post("/api/summaries", json={"paragraph_id": 999, "user_text": SAID}).status_code == 404
        assert c.post("/api/summaries", json={"paragraph_id": paragraph["id"], "user_text": " "}).status_code == 422
        c.delete(f"/api/sessions/{sid}")
        assert c.get(f"/api/summaries?session_id={sid}").status_code == 404


def test_the_answer_comes_before_the_feedback_and_the_session_hears_both(tmp_path):
    held = HeldExecutor()
    db, app = judging_app(tmp_path, SummaryCoach(FakeCli(), AGENT_DIR), held)
    with admin_client(app) as c:
        sid, paragraph = a_paragraph(c)
        db.changes = Recorder()
        summary = c.post("/api/summaries", json={"paragraph_id": paragraph["id"], "user_text": SAID}).json()
        assert (summary["status"], summary["feedback"]) == ("judging", None)
        assert db.changes.published == [(sid, SessionChange.RECORDS)]
        held.release()
        [judged] = c.get(f"/api/summaries?session_id={sid}").json()
        assert (judged["status"], judged["feedback"]) == ("done", ANSWER)
        assert db.changes.published == [(sid, SessionChange.RECORDS)] * 2


def test_a_failed_judgment_keeps_the_summary_to_judge_again_or_remove(tmp_path):
    db, app = judging_app(tmp_path, Down(), InlineExecutor())
    with admin_client(app) as c:
        sid, paragraph = a_paragraph(c)
        summary = c.post("/api/summaries", json={"paragraph_id": paragraph["id"], "user_text": SAID}).json()
        assert (summary["status"], summary["error"], summary["feedback"]) == ("failed", "feedback failed: down", None)

        app.state.services = Services(FakeGenerator(), summary_coach=SummaryCoach(FakeCli(), AGENT_DIR))
        again = c.post(f"/api/summaries/{summary['id']}/judge")
        assert again.status_code == 200
        assert (again.json()["status"], again.json()["feedback"], again.json()["error"]) == ("done", ANSWER, None)
        refused = c.post(f"/api/summaries/{summary['id']}/judge")
        assert (refused.status_code, refused.json()["detail"]) == (409, AGAIN)
        kept = c.delete(f"/api/summaries/{summary['id']}")
        assert (kept.status_code, kept.json()["detail"]) == (409, NOT_REMOVED)

        app.state.services = Services(FakeGenerator(), summary_coach=Down())
        failed = c.post("/api/summaries", json={"paragraph_id": paragraph["id"], "user_text": SAID}).json()
        assert c.delete(f"/api/summaries/{failed['id']}").status_code == 204
        assert [s["id"] for s in c.get(f"/api/summaries?session_id={sid}").json()] == [summary["id"]]
        assert c.post("/api/summaries/999/judge").status_code == 404
        assert c.delete("/api/summaries/999").status_code == 404


def test_a_restart_turns_a_summary_still_judging_into_a_failure(tmp_path):
    db, app = judging_app(tmp_path, SummaryCoach(FakeCli(), AGENT_DIR), HeldExecutor())
    with admin_client(app) as c:
        sid, paragraph = a_paragraph(c)
        c.post("/api/summaries", json={"paragraph_id": paragraph["id"], "user_text": SAID})
    again = create_app(db, Services(FakeGenerator()), InlineExecutor())
    with admin_client(again) as c:
        [summary] = c.get(f"/api/summaries?session_id={sid}").json()
        assert (summary["status"], summary["error"]) == ("failed", RESTARTED)


def test_the_summary_round_is_503_without_a_voice_key(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), InlineExecutor(), judges=InlineExecutor())
    with admin_client(app) as c:
        assert c.post("/api/summary/sessions", json={"paragraph": PARAGRAPH}).status_code == 503
        _, paragraph = a_paragraph(c)
        off = c.post("/api/summaries", json={"paragraph_id": paragraph["id"], "user_text": "x"})
        assert (off.status_code, off.json()["detail"]) == (503, "summary coach is off: the summary-coach folder is missing")
        assert c.post("/api/summary/feedback", json={"paragraph": PARAGRAPH, "user_text": "x"}).status_code in (404, 405)


def test_a_judgment_whose_feedback_cannot_be_saved_fails_the_summary_and_gives_the_price_back(tmp_path, caplog):
    db = Database(tmp_path / "s.db")
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 10, by=mina.id)
    paragraph = db.sessions.create(sample_draft(), [], created_by=mina.id).content.article.paragraphs[0].id
    summary_id = db.records.start_summary(paragraph, mina.id, SAID, 1)
    hold = db.credits.hold(mina, "summary_feedback")

    class Locked:
        """The records, except that keeping the feedback finds the database locked every time."""

        def __getattr__(self, name):
            return getattr(db.records, name)

        def finish_summary(self, *args):
            raise sqlite3.OperationalError("database is locked")

    SummaryJudges(Locked(), db.credits, InlineExecutor()).judge(summary_id, SummaryCoach(FakeCli(), AGENT_DIR), hold)
    summary = db.records.get_summary(summary_id, mina.id)
    assert (summary.status, summary.error) == ("failed", NOT_SAVED)
    assert db.credits.balance(mina.id) == 10
    assert "could not be judged or saved" in caplog.text
