from datetime import date

import pytest

from app.db import Database
from app.llm import GenerationError
from app.main import create_app
from app.models import Category
from app.topics.daily import FRESH_COUNT, POOL_COUNT, REFILL_COUNT, DailyTopics
from app.topics.pool import pool_for_day
from app.wiring import Services
from tests.conftest import CURATED_TOPICS as TOPICS, admin_client
from tests.test_api import FakeGenerator, InlineExecutor

NEWS = [f"news topic {i}" for i in range(FRESH_COUNT)]
STOCK = [f"story {i}" for i in range(REFILL_COUNT)]


class FakeSource:
    def __init__(self, error: Exception | None = None, stories: list[str] = NEWS):
        self.calls = 0
        self.error = error
        self.stories = stories
        self.excluded: list[list[str]] = []

    def fetch(self, count: int, exclude: list[str]) -> list[str]:
        self.calls += 1
        self.excluded.append(list(exclude))
        if self.error:
            raise self.error
        return self.stories[:count]


class HeldExecutor:
    """Holds a fetch back until the test lets it run."""

    def __init__(self):
        self.queued = []

    def submit(self, fn, /, *args):
        self.queued.append((fn, args))

    def run_all(self):
        queued, self.queued = self.queued, []
        for fn, args in queued:
            fn(*args)


@pytest.fixture
def store(tmp_path) -> Database:
    return Database(tmp_path / "s.db")


def texts(topics) -> list[str]:
    return [t.text for t in topics]


def news_on(daily) -> list[str]:
    return [t.text for t in daily.listing().topics if t.category == Category.NEWS]


def parts(listing) -> tuple[list, bool]:
    return listing.topics, listing.pending


def test_pool_slice_holds_all_day_and_turns_over_at_midnight():
    today = pool_for_day(date(2026, 9, 14), 6, TOPICS)
    assert today == pool_for_day(date(2026, 9, 14), 6, TOPICS)
    assert today != pool_for_day(date(2026, 9, 15), 6, TOPICS)
    assert set(today) <= set(TOPICS)
    assert len(set(today)) == 6


def test_pool_slice_leaves_out_what_the_news_already_covers():
    taken = texts(TOPICS[:3])
    assert not set(texts(pool_for_day(date(2026, 9, 14), 6, TOPICS, exclude=taken))) & set(taken)


def test_the_day_starts_on_the_pool_then_keeps_what_the_news_gave(store):
    source = FakeSource()
    daily = DailyTopics(store.topics)

    topics, pending = parts(daily.listing())
    assert pending is False  # nothing asked for yet
    assert len(topics) == FRESH_COUNT + POOL_COUNT
    assert not set(texts(topics)) & set(NEWS)

    daily.ensure_fetched(source)
    topics, pending = parts(daily.listing())
    assert pending is False
    assert texts(topics[:FRESH_COUNT]) == NEWS
    assert {t.category for t in topics[:FRESH_COUNT]} == {Category.NEWS}
    assert Category.NEWS not in {t.category for t in topics[FRESH_COUNT:]}
    assert len(topics) == FRESH_COUNT + POOL_COUNT


def test_a_day_is_fetched_once(store):
    source = FakeSource()
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)
    daily.ensure_fetched(source)
    assert source.calls == 1


def test_a_restart_refills_the_stock_and_keeps_the_news_on_the_list(store):
    source = FakeSource(stories=STOCK)
    DailyTopics(store.topics).ensure_fetched(source)
    source.stories = [f"later story {i}" for i in range(REFILL_COUNT)]
    restarted = DailyTopics(store.topics)
    restarted.ensure_fetched(source)
    assert source.calls == 2
    assert source.excluded[-1] == STOCK[:FRESH_COUNT]
    assert texts(restarted.listing().topics[:FRESH_COUNT]) == STOCK[:FRESH_COUNT]
    restarted.refresh(source)
    assert texts(restarted.listing().topics[:FRESH_COUNT]) == source.stories[:FRESH_COUNT]


def test_an_empty_fetch_is_not_cached_and_is_tried_again(store):
    source = FakeSource()
    source.fetch = lambda count, exclude: []  # type: ignore[method-assign]
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)

    topics, pending = parts(daily.listing())
    assert set(topics) <= set(TOPICS)
    assert pending is False  # nothing is running until someone asks again
    assert "no stories" in daily.listing().error

    source.fetch = FakeSource().fetch  # type: ignore[method-assign]
    daily.ensure_fetched(source)
    assert texts(daily.listing().topics[:FRESH_COUNT]) == NEWS


def test_a_failed_fetch_leaves_a_full_list_of_pool_topics(store):
    source = FakeSource(GenerationError("claude timed out after 180s"))
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)

    topics, pending = parts(daily.listing())
    assert len(topics) == FRESH_COUNT + POOL_COUNT
    assert set(topics) <= set(TOPICS)
    assert pending is False  # the next request may try again, but nothing is running now
    assert daily.listing().error == "claude timed out after 180s"


def test_without_a_source_nothing_is_pending(store):
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(None)
    topics, pending = parts(daily.listing())
    assert pending is False
    assert len(topics) == FRESH_COUNT + POOL_COUNT


def test_endpoint_serves_the_news_half_once_it_lands(tmp_path):
    store = Database(tmp_path / "s.db")
    app = create_app(store, Services(FakeGenerator(), topic_source=FakeSource()), InlineExecutor())
    with admin_client(app) as c:
        first = c.get("/api/topics").json()
        # InlineExecutor runs the fetch during that first request
        assert [t["text"] for t in first["topics"][:FRESH_COUNT]] == NEWS or first["pending"] is True

        second = c.get("/api/topics").json()
        assert second["pending"] is False
        assert [t["text"] for t in second["topics"][:FRESH_COUNT]] == NEWS
        assert {t["category"] for t in second["topics"][:FRESH_COUNT]} == {"news"}
        assert all(t["category"] for t in second["topics"])


def test_refresh_deals_the_next_stories_from_the_stock_without_fetching(store):
    source = FakeSource(stories=STOCK)
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)
    before, _ = parts(daily.listing())
    assert texts(before[:FRESH_COUNT]) == STOCK[:FRESH_COUNT]

    daily.refresh(source)
    after, pending = parts(daily.listing())
    assert pending is False
    assert source.calls == 1
    assert texts(after[:FRESH_COUNT]) == STOCK[FRESH_COUNT : 2 * FRESH_COUNT]
    assert after[FRESH_COUNT:] != before[FRESH_COUNT:]
    assert len(after) == FRESH_COUNT + POOL_COUNT


def test_a_low_stock_is_refilled_with_stories_not_used_today(store):
    source = FakeSource(stories=STOCK)
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)
    while source.calls == 1:
        daily.refresh(source)
    assert set(source.excluded[-1]) == set(STOCK)  # everything shown or waiting


def test_a_refill_deals_only_what_is_new_and_nothing_twice(store):
    source = FakeSource(stories=STOCK)
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)
    source.stories = [STOCK[0], STOCK[1], "a new story"]
    hands = [news_on(daily)]
    for _ in range(REFILL_COUNT):
        daily.refresh(source)
        if news_on(daily) != hands[-1]:
            hands.append(news_on(daily))
    assert [story for hand in hands for story in hand] == [*STOCK, "a new story"]


def test_a_refill_with_nothing_new_keeps_the_news_up_and_says_nothing(store):
    source = FakeSource(stories=STOCK[:FRESH_COUNT])
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)
    before, _ = parts(daily.listing())
    source.stories = []
    daily.refresh(source)
    after, pending = parts(daily.listing())
    assert texts(after[:FRESH_COUNT]) == STOCK[:FRESH_COUNT]
    assert after[FRESH_COUNT:] != before[FRESH_COUNT:]
    assert pending is False and daily.listing().error is None


def test_a_failed_refill_keeps_the_news_up_and_says_nothing(store):
    source = FakeSource(stories=STOCK[:FRESH_COUNT])
    daily = DailyTopics(store.topics)
    daily.ensure_fetched(source)
    source.error = GenerationError("claude timed out after 240s")
    daily.refresh(source)
    assert texts(daily.listing().topics[:FRESH_COUNT]) == STOCK[:FRESH_COUNT]
    assert daily.listing().error is None


def test_a_refill_on_its_way_is_not_shown_as_waiting(store):
    executor = HeldExecutor()
    source = FakeSource(stories=STOCK[:2 * FRESH_COUNT])
    daily = DailyTopics(store.topics, executor)
    daily.ensure_fetched(source)
    executor.run_all()
    daily.refresh(source)
    assert texts(daily.listing().topics[:FRESH_COUNT]) == STOCK[FRESH_COUNT : 2 * FRESH_COUNT]
    assert len(executor.queued) == 1
    assert daily.listing().pending is False


def test_a_new_day_starts_with_a_new_stock(store):
    source = FakeSource(stories=STOCK)
    daily = DailyTopics(store.topics)
    daily.today = lambda: date(2026, 11, 1)  # type: ignore[method-assign]
    daily.ensure_fetched(source)
    daily.refresh(source)
    daily.today = lambda: date(2026, 11, 2)  # type: ignore[method-assign]
    source.stories = [f"next day {i}" for i in range(REFILL_COUNT)]
    assert daily.listing().pending is False
    daily.ensure_fetched(source)
    assert source.calls == 2
    assert source.excluded[-1] == []
    assert texts(daily.listing().topics[:FRESH_COUNT]) == source.stories[:FRESH_COUNT]


def test_a_fetch_that_lands_after_the_day_turned_is_dropped(store):
    executor = HeldExecutor()
    source = FakeSource(stories=STOCK)
    daily = DailyTopics(store.topics, executor)
    daily.today = lambda: date(2026, 11, 1)  # type: ignore[method-assign]
    daily.ensure_fetched(source)
    daily.today = lambda: date(2026, 11, 2)  # type: ignore[method-assign]
    daily.ensure_fetched(source)
    executor.queued[0][0](*executor.queued[0][1])
    assert store.topics.news("2026-11-01") is None
    assert store.topics.news("2026-11-02") is None


def test_refresh_without_a_source_still_redeals_the_pool(store):
    daily = DailyTopics(store.topics)
    before, _ = parts(daily.listing())
    daily.refresh(None)
    after, pending = parts(daily.listing())
    assert after != before
    assert pending is False


def test_refresh_endpoint_answers_with_the_next_stories_at_once(tmp_path):
    store = Database(tmp_path / "s.db")
    executor = HeldExecutor()
    app = create_app(store, Services(FakeGenerator(), topic_source=FakeSource(stories=STOCK)), executor)
    with admin_client(app) as c:
        assert c.get("/api/topics").json()["pending"] is True  # nothing to show yet: the first fetch of the day
        executor.run_all()
        assert c.get("/api/topics").json()["pending"] is False

        res = c.post("/api/topics/refresh").json()
        assert res["pending"] is False
        assert [t["text"] for t in res["topics"][:FRESH_COUNT]] == STOCK[FRESH_COUNT : 2 * FRESH_COUNT]
        assert executor.queued == []


def test_pending_is_true_only_while_a_fetch_is_in_flight(store):
    source = FakeSource()
    source.fetch = lambda count, exclude: []  # type: ignore[method-assign]
    executor = HeldExecutor()
    daily = DailyTopics(store.topics, executor)

    daily.ensure_fetched(source)
    assert daily.listing().pending is True
    daily.ensure_fetched(source)
    assert len(executor.queued) == 1  # one fetch at a time

    executor.run_all()
    assert daily.listing().pending is False  # it failed, and nothing else is running


def test_endpoint_reports_the_failure_until_a_fetch_succeeds(tmp_path):
    store = Database(tmp_path / "s.db")
    source = FakeSource(GenerationError("claude exited 1: no such tool"))
    app = create_app(store, Services(FakeGenerator(), topic_source=source), InlineExecutor())
    with admin_client(app) as c:
        assert c.get("/api/topics").json()["error"] == "claude exited 1: no such tool"
        source.error = None
        assert c.post("/api/topics/refresh").json()["error"] is None
