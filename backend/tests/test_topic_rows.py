import pytest

from app.db import Database
from app.db.topics import TopicInUse
from app.main import create_app
from app.models import Category
from app.wiring import Services
from tests.conftest import CURATED_TOPICS, admin_client, sample_draft
from tests.test_api import FakeGenerator, InlineExecutor


def test_a_new_file_starts_with_the_curated_topics(store):
    assert store.topics.curated() == CURATED_TOPICS
    assert store.topics.news("2026-10-26") is None


def test_a_days_news_is_replaced_whole_and_each_topic_is_kept_once(store):
    store.topics.set_news("2026-10-25", ["A", "B"])
    store.topics.set_news("2026-10-26", ["B", "C"])
    store.topics.set_news("2026-10-26", ["C", "D"])
    assert (store.topics.news("2026-10-25"), store.topics.news("2026-10-26")) == (["A", "B"], ["C", "D"])
    entries = {t.text: t for t in store.topics.list_all() if t.category == Category.NEWS}
    assert {text: e.news_days for text, e in entries.items()} == {"A": ["2026-10-25"], "B": ["2026-10-25"], "C": ["2026-10-26"], "D": ["2026-10-26"]}


def test_a_session_points_at_its_topic_and_a_typed_one_becomes_a_row(store):
    curated = CURATED_TOPICS[3]
    first = store.sessions.create(sample_draft(topic=curated.text), [])
    second = store.sessions.create(sample_draft(topic="Something of my own"), [])
    third = store.sessions.create(sample_draft(topic="Something of my own"), [])
    entries = {t.text: t for t in store.topics.list_all()}
    assert (entries[curated.text].category, entries[curated.text].sessions) == (curated.category, [first.id])
    assert (entries["Something of my own"].category, entries["Something of my own"].sessions) == (Category.TYPED, [second.id, third.id])
    assert store.sessions.get(second.id).topic == "Something of my own"
    assert store.sessions.recent_topics(5) == ["Something of my own", curated.text]
    assert all(t.category != Category.TYPED for t in store.topics.curated())


def test_every_topic_is_served_with_the_names_of_all_categories(tmp_path):
    db = Database(tmp_path / "s.db")
    session = db.sessions.create(sample_draft(topic="Typed one"), [])
    with admin_client(create_app(db, Services(FakeGenerator()), InlineExecutor())) as c:
        body = c.get("/api/topics/all").json()
    assert len(body["topics"]) == len(CURATED_TOPICS) + 1
    last = body["topics"][-1]
    assert (last["text"], last["category"], last["news_days"], last["sessions"]) == ("Typed one", "typed", [], [session.id])
    assert body["labels"]["typed"] == "Typed in" and body["labels"]["news"] == "In the news"


def ids_by_text(store) -> dict[str, int]:
    return {t.text: t.id for t in store.topics.list_all()}


def test_a_topic_no_session_uses_is_deleted_with_its_news_days(store):
    store.topics.set_news("2026-10-26", ["A", "B", "C"])
    ids = ids_by_text(store)
    assert store.topics.delete(ids["B"]) is True
    assert store.topics.news("2026-10-26") == ["A", "C"]
    assert "B" not in ids_by_text(store)
    assert store.topics.delete(ids[CURATED_TOPICS[0].text]) is True
    assert CURATED_TOPICS[0] not in store.topics.curated()
    assert store.topics.delete(ids["B"]) is False


def test_a_topic_a_session_uses_stays(store):
    store.sessions.create(sample_draft(topic="Mine"), [])
    with pytest.raises(TopicInUse):
        store.topics.delete(ids_by_text(store)["Mine"])
    assert "Mine" in ids_by_text(store)


def test_a_topic_is_deleted_over_http_unless_a_session_uses_it(tmp_path):
    db = Database(tmp_path / "s.db")
    db.sessions.create(sample_draft(topic="Mine"), [])
    ids = ids_by_text(db)
    with admin_client(create_app(db, Services(FakeGenerator()), InlineExecutor())) as c:
        assert c.delete(f"/api/topics/{ids['Mine']}").status_code == 409
        assert c.delete(f"/api/topics/{ids[CURATED_TOPICS[0].text]}").status_code == 204
        assert c.delete(f"/api/topics/{ids[CURATED_TOPICS[0].text]}").status_code == 404
