import sqlite3
import threading
from datetime import timedelta

import pytest

from app.credits import CONFIRM_WINDOW, PRICES, REPORT_WINDOW
from app.db import Database
from app.db.credits import NotEnoughCredits
from app.generation.jobs import EXPRESSION_COUNT
from app.live.changes import AccountChange
from app.llm import GenerationError
from app.main import create_app
from app.models import ExampleFeedback, SummaryFeedback
from app.net import HttpError
from app.wiring import Services
from tests.conftest import add_user, admin_client, client_of, seed_expressions
from tests.test_api import DeferredExecutor, FailingGenerator, FakeGenerator, InlineExecutor


def test_a_new_account_has_nothing_and_a_grant_shows_up_first(store):
    mina = add_user(store, "mina@example.com")
    admin = add_user(store, "boss@example.com", admin=True)
    assert store.credits.balance(mina.id) == 0 and store.credits.recent(mina.id) == []
    store.credits.grant(mina.id, 500, by=admin.id)
    assert store.credits.balance(mina.id) == 500
    (entry,) = store.credits.recent(mina.id)
    assert (entry.amount, entry.kind, entry.detail) == (500, "grant", None)


def test_recent_is_newest_first_and_stops_at_the_limit(store):
    mina = add_user(store, "mina@example.com")
    for amount in range(1, 13):
        store.credits.grant(mina.id, amount, by=mina.id)
    assert [e.amount for e in store.credits.recent(mina.id)] == list(range(12, 2, -1))
    assert len(store.credits.recent(mina.id, limit=3)) == 3


def test_my_credits_show_the_balance_the_prices_and_the_last_charges(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 30, by=mina.id)
    db.credits.settle(db.credits.hold(mina, "redraw", "sprawl"))
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


def test_feedback_costs_10_and_a_failing_coach_takes_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 25, example_coach=Coach())
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 200
    assert db.credits.balance(mina.id) == 15
    me.app.state.services.example_coach = Coach(fail=True)
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 502
    assert db.credits.balance(mina.id) == 15
    assert [(e.kind, e.detail) for e in db.credits.recent(mina.id)] == [("practice_feedback", "mitigate"), ("grant", None)]


class CrashingCoach:
    """Fails the way nothing in the route expects."""

    def feedback(self, *args):
        raise KeyError("candidates")


def test_an_error_no_route_expects_takes_nothing_either(tmp_path):
    db, mina, me = paid_world(tmp_path, 25, example_coach=CrashingCoach(), summary_coach=CrashingCoach())
    with pytest.raises(KeyError):
        me.post("/api/example/feedback", json=FEEDBACK_BODY)
    with pytest.raises(KeyError):
        me.post("/api/summary/feedback", json=PARAGRAPH | {"user_text": "It is words."})
    assert db.credits.balance(mina.id) == 25


def test_a_summary_coach_that_fails_takes_nothing(tmp_path):
    class Down:
        def feedback(self, paragraph, user_text):
            raise GenerationError("down")

    db, mina, me = paid_world(tmp_path, 25, summary_coach=Down())
    assert me.post("/api/summary/feedback", json=PARAGRAPH | {"user_text": "It is words."}).status_code == 502
    assert db.credits.balance(mina.id) == 25


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


def test_a_new_picture_costs_10_names_the_word_and_a_failed_drawing_takes_nothing(tmp_path):
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
    assert db.credits.balance(mina.id) == 10
    services.illustrator = Drawer(db)
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 200
    assert db.credits.balance(mina.id) == 0
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 402
    assert me.post(f"/api/sessions/{sid}/pictures/99", json={"face": "example"}).status_code == 404


def test_a_picture_for_a_session_deleted_while_drawing_takes_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 210)
    sid = me.post("/api/sessions", json={"topic": "Trams"}).json()["session_id"]

    class DeletesFirst(Drawer):
        def redraw_example(self, item):
            db.sessions.delete(sid)
            return super().redraw_example(item)

    services = me.app.state.services
    services.illustrator, services.scene_writer = DeletesFirst(db), object()
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 404
    assert db.credits.balance(mina.id) == 10


def test_the_admin_pays_nothing_at_a_paid_route(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator(), example_coach=Coach()), InlineExecutor())
    admin = admin_client(app)
    assert admin.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 200
    boss = db.accounts.by_email("admin@example.com")
    assert db.credits.recent(boss.id) == []


def test_a_failed_generation_costs_nothing(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FailingGenerator()), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 200, by=mina.id)
    me = client_of(app, db, mina)
    assert me.post("/api/sessions", json={"topic": "Trams"}).json()["status"] == "failed"
    assert db.credits.balance(mina.id) == 200
    assert [e.kind for e in db.credits.recent(mina.id)] == ["grant"]


def test_the_admins_failed_generation_writes_nothing(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FailingGenerator()), InlineExecutor())
    assert admin_client(app).post("/api/sessions", json={"topic": "Trams"}).json()["status"] == "failed"
    assert db.credits.recent(db.accounts.by_email("admin@example.com").id) == []


class ShutDownExecutor:
    def submit(self, fn, /, *args):
        raise RuntimeError("cannot schedule new futures after shutdown")


def test_a_session_the_server_could_not_start_gives_the_200_back(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), ShutDownExecutor())
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 200, by=mina.id)
    res = client_of(app, db, mina).post("/api/sessions", json={"topic": "Trams"})
    assert res.status_code == 202 and res.json()["status"] == "failed"
    assert db.credits.balance(mina.id) == 200


def funded(store, amount: int):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, amount, by=mina.id)
    return mina


def kinds(store, user) -> list[str]:
    return [e.kind for e in store.credits.recent(user.id)]


def test_a_hold_takes_the_price_at_once_and_reads_like_a_charge(store):
    mina = funded(store, 15)
    store.credits.hold(mina, "redraw", "sprawl")
    assert store.credits.balance(mina.id) == 5
    entry = store.credits.recent(mina.id)[0]
    assert (entry.amount, entry.kind, entry.detail) == (-10, "redraw", "sprawl")


def test_a_hold_the_balance_cannot_cover_says_what_is_missing_and_leaves_no_row(store):
    mina = funded(store, 3)
    with pytest.raises(NotEnoughCredits) as refused:
        store.credits.hold(mina, "redraw")
    assert (refused.value.need, refused.value.have) == (10, 3)
    assert kinds(store, mina) == ["grant"]


def test_a_settled_hold_stays_and_a_released_one_is_as_if_it_never_was(store):
    mina = funded(store, 30)
    store.credits.settle(store.credits.hold(mina, "redraw"))
    store.credits.release(store.credits.hold(mina, "redraw"))
    assert store.credits.balance(mina.id) == 20
    assert kinds(store, mina) == ["redraw", "grant"]


def test_a_release_cannot_undo_what_was_settled(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "redraw")
    store.credits.settle(hold)
    store.credits.release(hold)
    assert store.credits.balance(mina.id) == 0


def test_settling_as_a_cancelled_session_takes_half_and_keeps_the_topic(store):
    mina = funded(store, 200)
    store.credits.settle(store.credits.hold(mina, "session", "Trams"), as_kind="session_cancelled")
    assert store.credits.balance(mina.id) == 100
    entry = store.credits.recent(mina.id)[0]
    assert (entry.amount, entry.kind, entry.detail) == (-100, "session_cancelled", "Trams")
    assert PRICES["session_cancelled"] == 100


def test_the_admin_holds_nothing_and_every_step_on_that_does_nothing(store):
    boss = add_user(store, "boss@example.com", admin=True)
    hold = store.credits.hold(boss, "session", "Trams")
    assert hold is None
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    store.credits.settle(hold)
    store.credits.release(hold)
    assert store.credits.recent(boss.id) == []


def test_two_holds_at_once_on_one_price_worth_of_balance_let_only_one_through(store):
    mina = funded(store, 10)
    results: list[str] = []
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        try:
            store.credits.hold(mina, "redraw")
            results.append("held")
        except NotEnoughCredits:
            results.append("refused")

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["held", "refused"]
    assert store.credits.balance(mina.id) == 0


def test_a_browser_hold_stops_counting_when_its_window_passes(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, timedelta(seconds=-1))
    assert store.credits.balance(mina.id) == 10
    assert kinds(store, mina) == ["grant"]
    assert store.credits.confirm(hold, mina.id, REPORT_WINDOW) is False
    assert store.credits.give_back(hold, mina.id) is False
    assert store.credits.balance(mina.id) == 10


def test_a_confirmed_round_is_paid_and_can_be_given_back_once(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    assert store.credits.confirm(hold, mina.id, REPORT_WINDOW) is True
    assert store.credits.balance(mina.id) == 0
    assert store.credits.give_back(hold, mina.id) is True
    assert store.credits.balance(mina.id) == 10
    assert store.credits.give_back(hold, mina.id) is False


def test_a_confirmed_round_is_final_once_the_report_window_passes(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    assert store.credits.confirm(hold, mina.id, timedelta(seconds=-1)) is True
    assert store.credits.give_back(hold, mina.id) is False
    assert store.credits.balance(mina.id) == 0


def test_nobody_else_can_confirm_or_give_back_a_hold(store):
    mina = funded(store, 10)
    other = add_user(store, "other@example.com")
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    assert store.credits.confirm(hold, other.id, REPORT_WINDOW) is False
    assert store.credits.give_back(hold, other.id) is False
    assert store.credits.balance(mina.id) == 0


def test_the_browser_cannot_touch_what_the_server_is_still_working_on(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "redraw")
    assert store.credits.confirm(hold, mina.id, REPORT_WINDOW) is False
    assert store.credits.give_back(hold, mina.id) is False
    assert store.credits.balance(mina.id) == 0


def test_a_released_hold_keeps_its_number_so_a_late_report_cannot_touch_the_next(store):
    mina = funded(store, 20)
    first = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(first, CONFIRM_WINDOW)
    assert store.credits.give_back(first, mina.id) is True
    second = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(second, CONFIRM_WINDOW)
    assert second != first
    assert store.credits.give_back(first, mina.id) is False
    assert store.credits.balance(mina.id) == 10


def test_holds_a_dead_process_left_are_released_and_settled_rows_stay(store):
    mina = funded(store, 30)
    store.credits.settle(store.credits.hold(mina, "redraw"))
    store.credits.hold(mina, "redraw")
    store.credits.release_abandoned()
    assert store.credits.balance(mina.id) == 20


def test_only_what_changes_the_balance_tells_the_account_to_read_it_again(store, recorder):
    mina = add_user(store, "mina@example.com")
    boss = add_user(store, "boss@example.com", admin=True)
    store.credits.grant(mina.id, 10, by=boss.id)
    hold = store.credits.hold(mina, "speech")
    store.credits.settle(hold)
    assert recorder.published == [(mina.id, AccountChange.CREDITS)] * 2
    store.credits.release(store.credits.hold(mina, "speech"))
    store.credits.hold(boss, "speech")
    assert recorder.published == [(mina.id, AccountChange.CREDITS)] * 4


class DownRound:
    def start(self, *args, **values) -> dict:
        raise HttpError(502, "down")


class DownAssessor:
    def session(self) -> dict:
        raise HttpError(502, "down")


VOICE_ROUTES = [("/api/example/sessions", WORD, 10), ("/api/summary/sessions", PARAGRAPH, 10), ("/api/read-aloud/sessions", PARAGRAPH, 5)]


@pytest.mark.parametrize("path,body,price", VOICE_ROUTES)
def test_a_voice_round_the_provider_refuses_takes_nothing(tmp_path, path, body, price):
    agents = {"example": DownRound(), "read-aloud": DownRound()}
    db, mina, me = paid_world(tmp_path, price, agents=agents, transcriber=DownRound())
    assert me.post(path, json=body).status_code == 502
    assert db.credits.balance(mina.id) == price


def test_an_assessor_token_the_provider_refuses_takes_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 5, assessor=DownAssessor())
    assert me.get("/api/assessor/token").status_code == 502
    assert db.credits.balance(mina.id) == 5


@pytest.mark.parametrize("path,body,price", VOICE_ROUTES)
def test_a_voice_round_hands_over_its_hold_which_the_browser_settles_or_gives_back(tmp_path, path, body, price):
    agents = {"example": LiveRound(), "read-aloud": LiveRound()}
    db, mina, me = paid_world(tmp_path, price, agents=agents, transcriber=LiveRound())
    hold = me.post(path, json=body).json()["hold"]
    assert db.credits.balance(mina.id) == 0
    assert me.post(f"/api/me/credits/holds/{hold}/confirm").status_code == 204
    assert db.credits.balance(mina.id) == 0
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 204
    assert db.credits.balance(mina.id) == price
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 404


def test_the_assessor_token_carries_its_hold_too(tmp_path):
    db, mina, me = paid_world(tmp_path, 5, assessor=Assessor())
    hold = me.get("/api/assessor/token").json()["hold"]
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 204
    assert db.credits.balance(mina.id) == 5


def test_a_round_never_confirmed_comes_back_and_a_late_confirm_cannot_revive_it(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.deps.CONFIRM_WINDOW", timedelta(seconds=-1))
    db, mina, me = paid_world(tmp_path, 10, agents={"example": LiveRound()})
    hold = me.post("/api/example/sessions", json=WORD).json()["hold"]
    assert db.credits.balance(mina.id) == 10
    assert me.post(f"/api/me/credits/holds/{hold}/confirm").status_code == 404
    assert db.credits.balance(mina.id) == 10


def test_nobody_else_can_report_on_my_hold(tmp_path):
    db, mina, me = paid_world(tmp_path, 10, agents={"example": LiveRound()})
    hold = me.post("/api/example/sessions", json=WORD).json()["hold"]
    other = client_of(me.app, db, add_user(db, "other@example.com"))
    assert other.post(f"/api/me/credits/holds/{hold}/confirm").status_code == 404
    assert other.delete(f"/api/me/credits/holds/{hold}").status_code == 404
    assert db.credits.balance(mina.id) == 0


def test_the_browser_cannot_give_back_what_the_server_is_working_on(tmp_path):
    db, mina, me = paid_world(tmp_path, 10)
    hold = db.credits.hold(mina, "redraw")
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 404
    assert db.credits.balance(mina.id) == 0


def test_the_admins_round_has_no_hold(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator(), agents={"example": LiveRound()}), InlineExecutor())
    assert admin_client(app).post("/api/example/sessions", json=WORD).json()["hold"] is None


class Pictures:
    """Stands in for the illustrator: `during` runs while it draws, then it fails or reports what did not come back."""

    def __init__(self, missing=0, error=None, during=None):
        self.missing, self.error, self.during = missing, error, during

    def expected_seconds(self, count):
        return None

    def count(self, words, scenes):
        return 1

    def illustrate(self, job_id, words, on_drawn, on_picture, scenes, on_figure):
        if self.during:
            self.during(job_id)
        on_drawn(1)
        if self.error:
            raise self.error
        return self.missing


def make_session(me) -> dict:
    return me.post("/api/sessions", json={"topic": "Trams"}).json()


def queued_world(tmp_path, balance: int, generator=None):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    executor = DeferredExecutor()
    app = create_app(db, Services(generator or FakeGenerator()), executor)
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, balance, by=mina.id)
    return db, mina, client_of(app, db, mina), executor


def test_a_session_with_every_picture_costs_200_and_stays(tmp_path):
    db, mina, me = paid_world(tmp_path, 250, illustrator=Pictures())
    job = make_session(me)
    assert job["status"] == "done" and db.credits.balance(mina.id) == 50
    assert me.get(f"/api/sessions/{job['session_id']}").status_code == 200


@pytest.mark.parametrize(
    "pictures,status",
    [
        (Pictures(missing=1), "done"),
        (Pictures(error=GenerationError("openrouter down")), "done"),
        (Pictures(error=OSError("No space left on device")), "failed"),
    ],
)
def test_a_session_short_of_what_it_promised_stays_and_costs_nothing(tmp_path, pictures, status):
    db, mina, me = paid_world(tmp_path, 200, illustrator=pictures)
    job = make_session(me)
    assert job["status"] == status and job["session_id"] is not None
    assert db.credits.balance(mina.id) == 200
    assert [e.kind for e in db.credits.recent(mina.id)] == ["grant"]
    assert me.get(f"/api/sessions/{job['session_id']}").status_code == 200


def test_cancelling_while_the_pictures_are_drawn_deletes_the_session_and_costs_half(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)
    me.app.state.services.illustrator = Pictures(during=lambda job_id: me.delete(f"/api/jobs/{job_id}"))
    job = make_session(me)
    assert job["status"] == "cancelled" and job["session_id"] is None
    assert me.get("/api/sessions").json() == []
    assert db.credits.balance(mina.id) == 100
    entry = db.credits.recent(mina.id)[0]
    assert (entry.amount, entry.kind, entry.detail) == (-100, "session_cancelled", "Trams")


def test_cancelling_after_claude_was_called_costs_half_even_before_the_session_is_saved(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)

    class CancelsWhileWriting(FakeGenerator):
        def generate(self, topic, on_progress=None, exclude=None):
            me.delete(f"/api/jobs/{me.get('/api/jobs').json()[0]['id']}")
            return super().generate(topic, on_progress, exclude)  # its progress report raises Cancelled

    me.app.state.services.generator = CancelsWhileWriting()
    assert make_session(me)["status"] == "cancelled"
    assert db.credits.balance(mina.id) == 100


def test_cancelling_a_job_still_in_the_queue_costs_nothing(tmp_path):
    db, mina, me, executor = queued_world(tmp_path, 200)
    job = make_session(me)
    assert me.get(f"/api/jobs/{job['id']}").json()["spent"] is False
    me.delete(f"/api/jobs/{job['id']}")
    executor.run()
    assert db.credits.balance(mina.id) == 200


def test_the_second_session_at_once_is_refused_and_the_firsts_failure_gives_all_back(tmp_path):
    db, mina, me, executor = queued_world(tmp_path, 300, FailingGenerator())
    make_session(me)
    second = me.post("/api/sessions", json={"topic": "Boats"})
    assert second.status_code == 402
    assert second.json()["detail"] == "Not enough credits: this needs 200 and you have 100."
    executor.run()
    assert db.credits.balance(mina.id) == 300


def test_a_cancel_after_the_job_is_done_is_too_late(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)
    job = make_session(me)
    assert me.delete(f"/api/jobs/{job['id']}").json()["status"] == "done"
    assert db.credits.balance(mina.id) == 0
    assert me.get(f"/api/sessions/{job['session_id']}").status_code == 200


def test_the_admins_cancelled_session_goes_too_and_writes_nothing(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    admin = admin_client(app)
    app.state.services.illustrator = Pictures(during=lambda job_id: admin.delete(f"/api/jobs/{job_id}"))
    assert make_session(admin)["status"] == "cancelled"
    assert admin.get("/api/sessions").json() == []
    assert db.credits.recent(db.accounts.by_email("admin@example.com").id) == []


def test_a_session_still_being_drawn_cannot_be_deleted(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)
    answers = []

    def try_to_delete(job_id):
        sid = me.get(f"/api/jobs/{job_id}").json()["session_id"]
        answers.append(me.delete(f"/api/sessions/{sid}"))

    me.app.state.services.illustrator = Pictures(during=try_to_delete)
    job = make_session(me)
    assert answers[0].status_code == 409
    assert answers[0].json()["detail"] == "This session is still being drawn. Cancel it on the progress bar: the session goes and half the price stays charged."
    assert job["status"] == "done" and db.credits.balance(mina.id) == 0
    assert me.delete(f"/api/sessions/{job['session_id']}").status_code == 204
    assert db.credits.balance(mina.id) == 0  # a finished session stays paid for


def test_a_cancel_acknowledged_at_the_very_end_is_not_overwritten_by_done(tmp_path, monkeypatch):
    db, mina, me = paid_world(tmp_path, 200)
    add_stage = db.stages.add
    answers = []

    def cancelling_first(stage, seconds):
        if not answers:
            answers.append(me.delete(f"/api/jobs/{me.get('/api/jobs').json()[0]['id']}").json()["status"])
        add_stage(stage, seconds)

    monkeypatch.setattr(db.stages, "add", cancelling_first)
    job = make_session(me)
    assert answers == ["cancelled"]
    assert job["status"] == "cancelled" and job["session_id"] is None
    assert me.get("/api/sessions").json() == []
    assert db.credits.balance(mina.id) == 100


def test_a_job_reads_as_spent_from_the_moment_its_worker_takes_it(tmp_path, monkeypatch):
    db, _, me = paid_world(tmp_path, 200)
    used_words = db.sessions.used_words
    seen = []

    def looking(**kwargs):
        seen.append(me.get("/api/jobs").json()[0]["spent"])
        return used_words(**kwargs)

    monkeypatch.setattr(db.sessions, "used_words", looking)
    make_session(me)
    assert seen == [True]


def test_a_session_whose_job_failed_can_be_deleted_and_stays_free(tmp_path):
    db, mina, me = paid_world(tmp_path, 200, illustrator=Pictures(error=OSError("disk")))
    job = make_session(me)
    assert me.delete(f"/api/sessions/{job['session_id']}").status_code == 204
    assert db.credits.balance(mina.id) == 200


def busy_for(store, monkeypatch, times: int) -> list[int]:
    """The next `times` connections find the database busy. What is left of them, to look at afterwards."""
    connect = store.connect
    left = [times]

    def flaky():
        if left[0] > 0:
            left[0] -= 1
            raise sqlite3.OperationalError("database is locked")
        return connect()

    monkeypatch.setattr(store, "connect", flaky)
    monkeypatch.setattr("app.db.retry.time.sleep", lambda _: None)
    return left


def test_a_busy_moment_does_not_leave_a_hold_open(store, monkeypatch):
    mina = funded(store, 30)
    kept, gone = store.credits.hold(mina, "redraw"), store.credits.hold(mina, "redraw")
    busy_for(store, monkeypatch, 2)
    store.credits.settle(kept)
    busy_for(store, monkeypatch, 2)
    store.credits.release(gone)
    store.credits.release_abandoned()  # were the first still held, this would give it back too
    assert store.credits.balance(mina.id) == 20


def test_a_database_that_stays_busy_is_tried_three_times_then_said_out_loud(store, monkeypatch):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "redraw")
    left = busy_for(store, monkeypatch, 99)
    with pytest.raises(sqlite3.OperationalError):
        store.credits.release(hold)
    assert left == [96]


def test_a_round_nobody_confirmed_reads_as_released_once_anyone_spends_and_live_holds_do_not(store):
    mina = funded(store, 30)
    other = add_user(store, "other@example.com")
    store.credits.grant(other.id, 1, by=mina.id)
    expired = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(expired, timedelta(seconds=-1))
    waiting = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(waiting, CONFIRM_WINDOW)
    working = store.credits.hold(mina, "redraw")
    store.credits.hold(other, "speech")
    with store.connect() as conn:
        states = {row["id"]: row["state"] for row in conn.execute("SELECT id, state FROM credits")}
    assert (states[expired], states[waiting], states[working]) == ("released", "held", "held")
    assert store.credits.balance(mina.id) == 10


def test_a_cancelled_session_that_will_not_go_stays_named_on_the_job_and_costs_half(tmp_path, monkeypatch):
    db, mina, me = paid_world(tmp_path, 200)

    def refuses(session_id):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db.sessions, "delete", refuses)
    monkeypatch.setattr("app.db.retry.time.sleep", lambda _: None)
    me.app.state.services.illustrator = Pictures(during=lambda job_id: me.delete(f"/api/jobs/{job_id}"))
    job = make_session(me)
    assert job["status"] == "cancelled" and job["session_id"] is not None
    assert me.get(f"/api/sessions/{job['session_id']}").status_code == 200
    assert db.credits.balance(mina.id) == 100


def test_a_restart_gives_back_what_the_dead_process_held(tmp_path):
    db, mina, _ = paid_world(tmp_path, 200)
    db.credits.hold(mina, "session", "Trams")
    assert db.credits.balance(mina.id) == 0
    create_app(db, Services(FakeGenerator()), InlineExecutor())
    assert db.credits.balance(mina.id) == 200


def test_a_gift_moves_credits_and_each_side_reads_who_it_was(store):
    mina = funded(store, 300)
    jun = add_user(store, "jun@example.com")
    store.credits.gift(mina, jun, 200)
    assert (store.credits.balance(mina.id), store.credits.balance(jun.id)) == (100, 200)
    sent, received = store.credits.recent(mina.id)[0], store.credits.recent(jun.id)[0]
    assert (sent.amount, sent.kind, sent.detail) == (-200, "gift_sent", "jun")
    assert (received.amount, received.kind, received.detail) == (200, "gift_received", "mina")
    with store.connect() as conn:
        givers = [row[0] for row in conn.execute("SELECT granted_by FROM credits WHERE kind LIKE 'gift_%' ORDER BY id")]
    assert givers == [mina.id, mina.id]


def test_a_gift_beyond_the_balance_moves_nothing(store):
    mina = funded(store, 150)
    jun = add_user(store, "jun@example.com")
    with pytest.raises(NotEnoughCredits) as refused:
        store.credits.gift(mina, jun, 200)
    assert (refused.value.need, refused.value.have) == (200, 150)
    assert (store.credits.balance(mina.id), store.credits.balance(jun.id)) == (150, 0)
    assert store.credits.recent(jun.id) == []


def test_credits_held_for_running_work_cannot_be_gifted(store):
    mina = funded(store, 250)
    jun = add_user(store, "jun@example.com")
    store.credits.hold(mina, "session", "Trams")
    with pytest.raises(NotEnoughCredits) as refused:
        store.credits.gift(mina, jun, 100)
    assert (refused.value.need, refused.value.have) == (100, 50)


def test_two_gifts_at_once_on_one_gift_worth_of_balance_let_only_one_through(store):
    mina = funded(store, 200)
    jun = add_user(store, "jun@example.com")
    results: list[str] = []
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        try:
            store.credits.gift(mina, jun, 200)
            results.append("given")
        except NotEnoughCredits:
            results.append("refused")

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["given", "refused"]
    assert (store.credits.balance(mina.id), store.credits.balance(jun.id)) == (0, 200)


def test_a_gift_tells_both_accounts_to_read_their_credits_again(store, recorder):
    mina = funded(store, 300)
    jun = add_user(store, "jun@example.com")
    recorder.published.clear()
    store.credits.gift(mina, jun, 50)
    assert recorder.published == [(mina.id, AccountChange.CREDITS), (jun.id, AccountChange.CREDITS)]


def gift_world(tmp_path):
    """mina with 300 credits and jun with none, and the app they use."""
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    mina = funded(db, 300)
    jun = add_user(db, "jun@example.com")
    return db, app, mina, jun


def test_a_gift_through_the_route_answers_204_and_moves_the_credits(tmp_path):
    db, app, mina, jun = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": jun.id, "amount": 200})
    assert answer.status_code == 204
    assert (db.credits.balance(mina.id), db.credits.balance(jun.id)) == (100, 200)


def test_a_gift_to_oneself_is_refused(tmp_path):
    db, app, mina, _ = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": mina.id, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (400, "You cannot gift credits to yourself.")
    assert db.credits.balance(mina.id) == 300


def test_a_gift_to_the_admin_is_refused(tmp_path):
    db, app, mina, _ = gift_world(tmp_path)
    boss = add_user(db, "boss@example.com", admin=True)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": boss.id, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (400, "The admin is not charged, so there is nothing to add to.")
    assert db.credits.balance(mina.id) == 300


def test_the_admin_has_no_credits_to_give(tmp_path):
    db, app, _, jun = gift_world(tmp_path)
    answer = admin_client(app).post("/api/me/credits/gifts", json={"to": jun.id, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (400, "The admin has no credits to give.")
    assert db.credits.balance(jun.id) == 0


def test_a_gift_to_no_account_is_not_found(tmp_path):
    db, app, mina, _ = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": 999, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (404, "account not found")


@pytest.mark.parametrize("amount", [0, -5])
def test_a_gift_of_nothing_or_less_is_not_a_gift(tmp_path, amount):
    db, app, mina, jun = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": jun.id, "amount": amount})
    assert answer.status_code == 422
    assert (db.credits.balance(mina.id), db.credits.balance(jun.id)) == (300, 0)


def test_a_gift_beyond_the_balance_says_what_it_needs(tmp_path):
    db, app, mina, jun = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": jun.id, "amount": 500})
    assert (answer.status_code, answer.json()["detail"]) == (402, "Not enough credits: this needs 500 and you have 300.")
