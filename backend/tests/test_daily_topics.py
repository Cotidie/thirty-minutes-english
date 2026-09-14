from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.claude_cli import GenerationError
from app.daily_topics import FRESH_COUNT, POOL_COUNT, DailyTopics
from app.main import create_app
from app.models import Category
from app.store import SessionStore
from app.topics import TOPICS, pool_for_day
from tests.test_api import FakeGenerator, InlineExecutor

NEWS = [f"news topic {i}" for i in range(FRESH_COUNT)]


class FakeSource:
    def __init__(self, error: Exception | None = None):
        self.calls = 0
        self.error = error

    def fetch(self, count: int) -> list[str]:
        self.calls += 1
        if self.error:
            raise self.error
        return NEWS[:count]


@pytest.fixture
def store(tmp_path) -> SessionStore:
    return SessionStore(tmp_path / "s.db")


def texts(topics) -> list[str]:
    return [t.text for t in topics]


def test_pool_slice_holds_all_day_and_turns_over_at_midnight():
    today = pool_for_day(date(2026, 9, 14), 6)
    assert today == pool_for_day(date(2026, 9, 14), 6)
    assert today != pool_for_day(date(2026, 9, 15), 6)
    assert set(today) <= set(TOPICS)
    assert len(set(today)) == 6


def test_pool_slice_leaves_out_what_the_news_already_covers():
    taken = texts(TOPICS[:3])
    assert not set(texts(pool_for_day(date(2026, 9, 14), 6, exclude=taken))) & set(taken)


def test_the_day_starts_on_the_pool_then_keeps_what_the_news_gave(store):
    source = FakeSource()
    daily = DailyTopics(store, source)

    topics, pending = daily.listing()
    assert pending is True
    assert len(topics) == FRESH_COUNT + POOL_COUNT
    assert not set(texts(topics)) & set(NEWS)

    daily.ensure_fetched()
    topics, pending = daily.listing()
    assert pending is False
    assert texts(topics[:FRESH_COUNT]) == NEWS
    assert {t.category for t in topics[:FRESH_COUNT]} == {Category.NEWS}
    assert Category.NEWS not in {t.category for t in topics[FRESH_COUNT:]}
    assert len(topics) == FRESH_COUNT + POOL_COUNT


def test_a_day_is_fetched_once(store):
    source = FakeSource()
    daily = DailyTopics(store, source)
    daily.ensure_fetched()
    daily.ensure_fetched()
    DailyTopics(store, source).ensure_fetched()  # a restart on the same day
    assert source.calls == 1


def test_an_empty_fetch_is_not_cached_and_is_tried_again(store):
    source = FakeSource()
    source.fetch = lambda count: []  # type: ignore[method-assign]
    daily = DailyTopics(store, source)
    daily.ensure_fetched()

    topics, pending = daily.listing()
    assert set(topics) <= set(TOPICS)
    assert pending is True

    source.fetch = FakeSource().fetch  # type: ignore[method-assign]
    daily.ensure_fetched()
    assert texts(daily.listing()[0][:FRESH_COUNT]) == NEWS


def test_a_failed_fetch_leaves_a_full_list_of_pool_topics(store):
    source = FakeSource(GenerationError("claude timed out after 180s"))
    daily = DailyTopics(store, source)
    daily.ensure_fetched()

    topics, pending = daily.listing()
    assert len(topics) == FRESH_COUNT + POOL_COUNT
    assert set(topics) <= set(TOPICS)
    assert pending is True  # it may still succeed later today


def test_without_a_source_nothing_is_pending(store):
    daily = DailyTopics(store, None)
    daily.ensure_fetched()
    topics, pending = daily.listing()
    assert pending is False
    assert len(topics) == FRESH_COUNT + POOL_COUNT


def test_endpoint_serves_the_news_half_once_it_lands(tmp_path):
    store = SessionStore(tmp_path / "s.db")
    app = create_app(store, FakeGenerator(), InlineExecutor(), topic_source=FakeSource())
    with TestClient(app) as c:
        first = c.get("/api/topics").json()
        # InlineExecutor runs the fetch during that first request
        assert [t["text"] for t in first["topics"][:FRESH_COUNT]] == NEWS or first["pending"] is True

        second = c.get("/api/topics").json()
        assert second["pending"] is False
        assert [t["text"] for t in second["topics"][:FRESH_COUNT]] == NEWS
        assert {t["category"] for t in second["topics"][:FRESH_COUNT]} == {"news"}
        assert all(t["category"] for t in second["topics"])


def test_refresh_redeals_the_pool_and_fetches_the_news_again(store):
    source = FakeSource()
    daily = DailyTopics(store, source)
    daily.ensure_fetched()
    before, _ = daily.listing()

    source.fetch = lambda count: [f"later news {i}" for i in range(count)]  # type: ignore[method-assign]
    daily.refresh()
    after, pending = daily.listing()
    assert pending is False  # the inline fetch already landed
    assert texts(after[:FRESH_COUNT]) == [f"later news {i}" for i in range(FRESH_COUNT)]
    assert after[FRESH_COUNT:] != before[FRESH_COUNT:]
    assert len(after) == FRESH_COUNT + POOL_COUNT


def test_refresh_without_a_source_still_redeals_the_pool(store):
    daily = DailyTopics(store, None)
    before, _ = daily.listing()
    daily.refresh()
    after, pending = daily.listing()
    assert after != before
    assert pending is False


def test_refresh_endpoint_reports_pending_until_the_news_lands(tmp_path):
    class SlowExecutor:
        def __init__(self):
            self.queued = []

        def submit(self, fn, /, *args):
            self.queued.append((fn, args))

    store = SessionStore(tmp_path / "s.db")
    executor = SlowExecutor()
    app = create_app(store, FakeGenerator(), executor, topic_source=FakeSource())
    with TestClient(app) as c:
        c.get("/api/topics")
        for fn, args in executor.queued:
            fn(*args)
        executor.queued.clear()
        assert c.get("/api/topics").json()["pending"] is False

        res = c.post("/api/topics/refresh").json()
        assert res["pending"] is True
        assert [t["text"] for t in res["topics"][:FRESH_COUNT]] == NEWS  # the old news half stays up meanwhile
        assert len(executor.queued) == 1

        for fn, args in executor.queued:
            fn(*args)
        assert c.get("/api/topics").json()["pending"] is False
