import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

from app.api.events import events_of
from app.db import Database
from app.live.changes import SessionChange, SessionChanges
from app.main import create_app
from app.models import Note, SummaryFeedback
from app.wiring import Services
from tests.conftest import add_user, sample_draft, seed_expressions, sign_in
from tests.test_api import FakeGenerator, InlineExecutor

FEEDBACK = SummaryFeedback(missed=[], fixes=[], summary="x")


class Recorder:
    def __init__(self):
        self.published: list[tuple[int, SessionChange]] = []

    def publish(self, session_id, change):
        self.published.append((session_id, change))


@pytest.fixture
def world(store):
    ids = seed_expressions(store, 3)
    session = store.sessions.create(sample_draft(), ids[:2])
    store.changes = Recorder()
    return store, session


@pytest.mark.parametrize(
    "write,expected",
    [
        (lambda db, s: db.sessions.set_note(s.id, Note(text="x")), {"note"}),
        (lambda db, s: db.sessions.set_star(s.id, "words", s.content.vocabulary[0].id, True), {"stars"}),
        (lambda db, s: db.sessions.add_expression(s.id), {"session"}),
        (lambda db, s: db.sessions.swap_expression(s.id, s.content.expressions[0].id), {"session", "stars"}),
        (lambda db, s: db.sessions.add_figure(s.id, None, db.pictures.add(None, None, None), "c", None, None), {"session"}),
        (lambda db, s: db.sessions.replace_picture(s.content.vocabulary[0].id, "image", db.pictures.add(None, None, None)), {"session"}),
        (lambda db, s: db.records.add_example(s.id, s.content.vocabulary[0].id, "u", "c", 1.0), {"records"}),
        (lambda db, s: db.records.add_summary(s.content.article.paragraphs[0].id, "u", FEEDBACK, 1.0), {"records"}),
        (lambda db, s: db.records.add_reading(s.content.article.paragraphs[0].id, "u", 1.0, []), {"records"}),
        (lambda db, s: db.expressions.delete(s.content.expressions[0].id), {"session"}),
        (lambda db, s: db.sessions.delete(s.id), {"access"}),
    ],
)
def test_every_write_says_what_changed(world, write, expected):
    db, session = world
    write(db, session)
    assert set(db.changes.published) == {(session.id, SessionChange(name)) for name in expected}


def test_a_read_says_nothing(world):
    db, session = world
    db.sessions.get(session.id)
    db.sessions.get_stars(session.id)
    db.sessions.get_note(session.id)
    db.records.list_examples(session.id)
    assert db.changes.published == []


def test_a_new_session_says_nothing_since_nobody_has_it_open(world):
    db, _ = world
    db.sessions.create(sample_draft(), [])
    assert db.changes.published == []


def test_unsharing_signals_access_and_a_share_that_was_not_there_does_not(world):
    db, session = world
    friend = add_user(db, "friend@example.com")
    db.shares.share(session.id, friend.id)
    assert db.changes.published == []
    db.shares.unshare(session.id, friend.id)
    assert db.changes.published == [(session.id, SessionChange.ACCESS)]
    db.shares.unshare(session.id, friend.id)
    assert db.changes.published == [(session.id, SessionChange.ACCESS)]


def test_a_write_that_fails_says_nothing(world):
    db, session = world
    with pytest.raises(KeyError):
        db.sessions.add_figure(999, None, db.pictures.add(None, None, None), "c", None, None)
    with pytest.raises(KeyError):
        db.sessions.replace_picture(999, "image", db.pictures.add(None, None, None))
    with pytest.raises(KeyError):
        db.records.add_example(session.id, 999, "u", "c", 1.0)
    assert db.sessions.delete(999) is None
    assert db.changes.published == []


def test_what_is_announced_is_already_committed(store):
    session = store.sessions.create(sample_draft(), [])
    seen = []

    class ReadsBack:
        def publish(self, session_id, change):
            seen.append(Database(store.path).sessions.get_note(session_id).text)

    store.changes = ReadsBack()
    store.sessions.set_note(session.id, Note(text="saved"))
    assert seen == ["saved"]


def run(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, 5))


def test_a_change_published_from_another_thread_wakes_the_reader():
    async def scenario():
        changes = SessionChanges()
        subscription = changes.subscribe(1)
        threading.Thread(target=changes.publish, args=(1, SessionChange.STARS)).start()
        assert await subscription.next(5) == {SessionChange.STARS}
        subscription.close()

    run(scenario())


def test_only_the_readers_of_that_session_hear():
    async def scenario():
        changes = SessionChanges()
        one, two = changes.subscribe(1), changes.subscribe(2)
        changes.publish(1, SessionChange.NOTE)
        await asyncio.sleep(0)
        assert await one.next(1) == {SessionChange.NOTE}
        assert await two.next(0.01) == set()

    run(scenario())


def test_a_burst_of_one_change_arrives_as_one_however_slow_the_reader():
    async def scenario():
        changes = SessionChanges()
        subscription = changes.subscribe(1)
        for _ in range(1000):
            changes.publish(1, SessionChange.SESSION)
        changes.publish(1, SessionChange.STARS)
        await asyncio.sleep(0)
        assert await subscription.next(1) == {SessionChange.SESSION, SessionChange.STARS}
        assert await subscription.next(0.01) == set()

    run(scenario())


def test_a_closed_reader_hears_nothing_and_publishing_with_no_readers_is_fine():
    async def scenario():
        changes = SessionChanges()
        changes.publish(1, SessionChange.NOTE)
        subscription = changes.subscribe(1)
        subscription.close()
        changes.publish(1, SessionChange.NOTE)
        await asyncio.sleep(0)
        assert await subscription.next(0.01) == set()

    run(scenario())


def test_publishing_after_the_readers_loop_is_gone_does_not_raise():
    changes = SessionChanges()

    async def leave_without_closing():
        changes.subscribe(1)

    asyncio.run(leave_without_closing())
    changes.publish(1, SessionChange.NOTE)


async def collect(stream, count):
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
        if len(chunks) == count:
            break
    return chunks


async def allowed():
    return True


def test_events_carry_only_a_name():
    async def scenario():
        changes = SessionChanges()
        subscription = changes.subscribe(1)
        changes.publish(1, SessionChange.STARS)
        await asyncio.sleep(0)
        return await collect(events_of(subscription, allowed, heartbeat_s=1), 2)

    assert run(scenario()) == ["retry: 5000\n\n", "event: stars\ndata: {}\n\n"]


def test_a_quiet_stream_sends_a_heartbeat():
    async def scenario():
        subscription = SessionChanges().subscribe(1)
        return await collect(events_of(subscription, allowed, heartbeat_s=0.01), 2)

    assert run(scenario())[1] == ": keep-alive\n\n"


def test_access_never_reaches_the_browser_while_i_am_allowed():
    async def scenario():
        changes = SessionChanges()
        subscription = changes.subscribe(1)
        changes.publish(1, SessionChange.ACCESS)
        await asyncio.sleep(0)
        stream = events_of(subscription, allowed, heartbeat_s=0.05)
        return await collect(stream, 2)

    assert run(scenario()) == ["retry: 5000\n\n", ": keep-alive\n\n"]


def test_losing_access_sends_gone_and_ends():
    async def refused():
        return False

    async def scenario():
        changes = SessionChanges()
        subscription = changes.subscribe(1)
        changes.publish(1, SessionChange.ACCESS)
        await asyncio.sleep(0)
        return await collect(events_of(subscription, refused, heartbeat_s=1), 10)

    assert run(scenario()) == ["retry: 5000\n\n", "event: gone\ndata: {}\n\n"]


def test_a_login_gone_stale_ends_the_stream_at_the_next_heartbeat():
    allowed_now = [True, False]

    async def still():
        return allowed_now.pop(0)

    async def scenario():
        subscription = SessionChanges().subscribe(1)
        return await collect(events_of(subscription, still, heartbeat_s=0.01), 10)

    assert run(scenario()) == ["retry: 5000\n\n", ": keep-alive\n\n", "event: gone\ndata: {}\n\n"]


def test_opening_the_stream_needs_a_login_and_access(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    me, stranger = add_user(db, "me@example.com"), add_user(db, "stranger@example.com")
    session = db.sessions.create(sample_draft(), [], created_by=me.id)
    client = TestClient(app)
    assert client.get(f"/api/sessions/{session.id}/events").status_code == 401
    sign_in(client, db, stranger)
    assert client.get(f"/api/sessions/{session.id}/events").status_code == 404
    assert client.get("/api/sessions/999/events").status_code == 404
