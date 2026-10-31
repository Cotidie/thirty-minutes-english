import threading

import pytest

from app.credits import PRICES
from app.db import Database
from app.generation.jobs import EXPRESSION_COUNT
from app.live.changes import AccountChange
from app.llm import GenerationError
from app.main import create_app
from app.models import ExampleFeedback, SummaryFeedback
from app.wiring import Services
from tests.conftest import add_user, admin_client, client_of, seed_expressions
from tests.test_api import FailingGenerator, FakeGenerator, InlineExecutor


def test_a_new_account_has_nothing_and_a_grant_shows_up_first(store):
    mina = add_user(store, "mina@example.com")
    admin = add_user(store, "boss@example.com", admin=True)
    assert store.credits.balance(mina.id) == 0 and store.credits.recent(mina.id) == []
    store.credits.grant(mina.id, 500, by=admin.id)
    assert store.credits.balance(mina.id) == 500
    (entry,) = store.credits.recent(mina.id)
    assert (entry.amount, entry.kind, entry.detail) == (500, "grant", None)


def test_a_charge_takes_the_price_and_names_what_it_was_for(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 15, by=mina.id)
    assert store.credits.charge(mina, "redraw", "sprawl") is True
    assert store.credits.balance(mina.id) == 5
    assert [(e.amount, e.kind, e.detail) for e in store.credits.recent(mina.id)] == [(-10, "redraw", "sprawl"), (15, "grant", None)]


def test_a_charge_the_balance_cannot_cover_leaves_no_row(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 3, by=mina.id)
    assert store.credits.charge(mina, "redraw") is False
    assert store.credits.balance(mina.id) == 3 and len(store.credits.recent(mina.id)) == 1


def test_the_admin_is_never_charged_and_nothing_is_written(store):
    boss = add_user(store, "boss@example.com", admin=True)
    assert store.credits.charge(boss, "session", "Trams") is True
    assert store.credits.recent(boss.id) == []


def test_a_refund_is_a_positive_row_of_its_own_kind(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 200, by=mina.id)
    store.credits.charge(mina, "session", "Trams")
    store.credits.refund(mina.id, PRICES["session"], "Trams")
    assert store.credits.balance(mina.id) == 200
    assert store.credits.recent(mina.id)[0].kind == "refund"


def test_recent_is_newest_first_and_stops_at_the_limit(store):
    mina = add_user(store, "mina@example.com")
    for amount in range(1, 13):
        store.credits.grant(mina.id, amount, by=mina.id)
    assert [e.amount for e in store.credits.recent(mina.id)] == list(range(12, 2, -1))
    assert len(store.credits.recent(mina.id, limit=3)) == 3


def test_two_charges_at_once_on_one_price_worth_of_balance_let_only_one_through(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 10, by=mina.id)
    results: list[bool] = []
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        results.append(store.credits.charge(mina, "redraw"))

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False, True]
    assert store.credits.balance(mina.id) == 0


def test_every_row_tells_the_account_to_read_its_credits_again(store, recorder):
    mina = add_user(store, "mina@example.com")
    boss = add_user(store, "boss@example.com", admin=True)
    store.credits.grant(mina.id, 10, by=boss.id)
    store.credits.charge(mina, "speech", "It was flawed.")
    store.credits.refund(mina.id, 1, None)
    store.credits.charge(boss, "speech")
    assert recorder.published == [(mina.id, AccountChange.CREDITS)] * 3


def test_my_credits_show_the_balance_the_prices_and_the_last_charges(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 30, by=mina.id)
    db.credits.charge(mina, "redraw", "sprawl")
    body = client_of(app, db, mina).get("/api/me/credits").json()
    assert body["balance"] == 20 and body["prices"] == PRICES
    assert [(e["amount"], e["kind"], e["detail"]) for e in body["recent"]] == [(-10, "redraw", "sprawl"), (30, "grant", None)]


def test_the_admin_has_no_balance_to_show(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    body = admin_client(app).get("/api/me/credits").json()
    assert body["balance"] is None and body["recent"] == [] and body["prices"]["session"] == 200


def test_topics_are_free_to_any_login(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    assert client_of(app, db, add_user(db, "mina@example.com")).get("/api/topics").status_code == 200


def paid_world(tmp_path, balance: int, **services):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    app = create_app(db, Services(FakeGenerator(), **services), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    if balance:
        db.credits.grant(mina.id, balance, by=mina.id)
    return db, mina, client_of(app, db, mina)


def test_making_a_session_costs_200_and_names_the_topic(tmp_path):
    db, mina, me = paid_world(tmp_path, 250)
    assert me.post("/api/sessions", json={"topic": "Trams"}).status_code == 202
    assert db.credits.balance(mina.id) == 50
    assert db.credits.recent(mina.id)[0].detail == "Trams"


def test_without_200_no_session_starts_and_the_answer_says_what_is_missing(tmp_path):
    db, mina, me = paid_world(tmp_path, 120)
    res = me.post("/api/sessions", json={"topic": "Trams"})
    assert res.status_code == 402 and res.json()["detail"] == "Not enough credits: this needs 200 and you have 120."
    assert me.get("/api/sessions").json() == [] and db.credits.balance(mina.id) == 120


class Coach:
    """Answers like the example coach, or fails like a provider that is down."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def feedback(self, word, pos, meaning, sentence, scene=""):
        if self.fail:
            raise GenerationError("down")
        return ExampleFeedback(paraphrase="The dam mitigates the flood.", feedback=["The verb agrees now."])


FEEDBACK_BODY = {"word": "mitigate", "pos": "verb", "meaning": "to lessen", "user_text": "The dam mitigate the flood.", "scene": "A dam in rain."}


def test_a_coach_that_is_off_charges_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 50)
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 503
    assert me.get("/api/assessor/token").status_code == 503
    assert me.post("/api/read-aloud/sessions", json={"paragraph": "Words."}).status_code == 503
    assert db.credits.balance(mina.id) == 50


def test_feedback_costs_10_and_a_failing_coach_keeps_the_charge(tmp_path):
    db, mina, me = paid_world(tmp_path, 25, example_coach=Coach())
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 200
    assert db.credits.balance(mina.id) == 15
    me.app.state.services.example_coach = Coach(fail=True)
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 502
    assert db.credits.balance(mina.id) == 5
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 402
    assert (db.credits.recent(mina.id)[0].kind, db.credits.recent(mina.id)[0].detail) == ("practice_feedback", "mitigate")


class Assessor:
    def session(self) -> dict:
        return {"token": "t", "region": "koreacentral", "word_score": 60}


def test_the_assessor_token_costs_5(tmp_path):
    db, mina, me = paid_world(tmp_path, 5, assessor=Assessor())
    assert me.get("/api/assessor/token").status_code == 200
    assert me.get("/api/assessor/token").status_code == 402
    assert db.credits.recent(mina.id)[0].kind == "read_aloud_token"


class LiveRound:
    """Stands in for an agent or the transcriber: whatever it is asked to start, the browser gets a socket."""

    def start(self, *args, **values) -> dict:
        return {"url": "wss://example.com", "setup": {}}


class SummaryCoach:
    def feedback(self, paragraph, user_text):
        return SummaryFeedback(missed=[], fixes=[], summary="x")


PARAGRAPH = {"paragraph": "Words."}
WORD = {"word": "mitigate", "meaning": "to lessen", "pos": "verb"}


@pytest.mark.parametrize(
    "path,body,kind,detail",
    [
        ("/api/example/sessions", WORD, "practice_voice", "mitigate"),
        ("/api/summary/sessions", PARAGRAPH, "summary_voice", None),
        ("/api/summary/feedback", PARAGRAPH | {"user_text": "It is words."}, "summary_feedback", None),
        ("/api/read-aloud/sessions", PARAGRAPH, "read_aloud_voice", None),
    ],
)
def test_each_coach_takes_its_own_price_and_then_refuses(tmp_path, path, body, kind, detail):
    agents = {"example": LiveRound(), "read-aloud": LiveRound()}
    db, mina, me = paid_world(tmp_path, PRICES[kind] + 1, agents=agents, transcriber=LiveRound(), summary_coach=SummaryCoach())
    assert me.post(path, json=body).status_code < 300
    entry = db.credits.recent(mina.id)[0]
    assert (entry.amount, entry.kind, entry.detail) == (-PRICES[kind], kind, detail)
    assert me.post(path, json=body).status_code == 402
    assert db.credits.balance(mina.id) == 1


def test_hearing_the_coach_is_charged_each_time(tmp_path):
    db, mina, me = paid_world(tmp_path, 12, agents={"read-aloud": LiveRound()})
    assert me.post("/api/read-aloud/sessions", json=PARAGRAPH).status_code == 201
    assert me.post("/api/read-aloud/sessions", json=PARAGRAPH).status_code == 201
    assert db.credits.balance(mina.id) == 2


class Drawer:
    """Stands in for the illustrator, adding a picture row or failing like a provider that is down."""

    def __init__(self, db: Database, fail: bool = False) -> None:
        self.db = db
        self.fail = fail

    def redraw_example(self, item) -> int:
        if self.fail:
            raise GenerationError("down")
        return self.db.pictures.add(None, None, None)


def test_a_new_picture_costs_10_names_the_word_and_a_failed_drawing_keeps_the_charge(tmp_path):
    db, mina, me = paid_world(tmp_path, 220)
    sid = me.post("/api/sessions", json={"topic": "Trams"}).json()["session_id"]
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 503
    assert db.credits.balance(mina.id) == 20
    services = me.app.state.services
    services.illustrator, services.scene_writer = Drawer(db), object()
    word = me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).json()["word"]
    assert (db.credits.balance(mina.id), db.credits.recent(mina.id)[0].kind, db.credits.recent(mina.id)[0].detail) == (10, "redraw", word)
    services.illustrator = Drawer(db, fail=True)
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 502
    assert db.credits.balance(mina.id) == 0
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 402
    assert me.post(f"/api/sessions/{sid}/pictures/99", json={"face": "example"}).status_code == 404


def test_the_admin_pays_nothing_at_a_paid_route(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator(), example_coach=Coach()), InlineExecutor())
    admin = admin_client(app)
    assert admin.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 200
    boss = db.accounts.by_email("admin@example.com")
    assert db.credits.recent(boss.id) == []


def test_a_failed_generation_gives_the_200_back_as_a_refund(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FailingGenerator()), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 200, by=mina.id)
    me = client_of(app, db, mina)
    assert me.post("/api/sessions", json={"topic": "Trams"}).json()["status"] == "failed"
    assert db.credits.balance(mina.id) == 200
    assert [(e.amount, e.kind, e.detail) for e in db.credits.recent(mina.id)[:2]] == [(200, "refund", "Trams"), (-200, "session", "Trams")]


def test_the_admins_failed_generation_writes_no_refund(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FailingGenerator()), InlineExecutor())
    assert admin_client(app).post("/api/sessions", json={"topic": "Trams"}).json()["status"] == "failed"
    assert db.credits.recent(db.accounts.by_email("admin@example.com").id) == []
