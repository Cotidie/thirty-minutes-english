from app.store import SessionStore
from tests.conftest import sample_content


def test_create_then_get_roundtrip(tmp_path, content):
    store = SessionStore(tmp_path / "s.db")
    created = store.create(content)
    fetched = store.get(created.id)
    assert fetched is not None
    assert fetched.topic == "Digital twins"
    assert fetched.content == content
    assert fetched.created_at == created.created_at


def test_list_returns_newest_first_with_title(tmp_path):
    store = SessionStore(tmp_path / "s.db")
    first = store.create(sample_content(topic="A", title="First"))
    second = store.create(sample_content(topic="B", title="Second"))
    summaries = store.list_all()
    assert [s.id for s in summaries] == [second.id, first.id]
    assert summaries[0].title == "Second"
    assert summaries[0].topic == "B"


def test_get_missing_returns_none(tmp_path):
    store = SessionStore(tmp_path / "s.db")
    assert store.get(999) is None


def test_delete_removes_session(tmp_path, content):
    store = SessionStore(tmp_path / "s.db")
    created = store.create(content)
    assert store.delete(created.id) is True
    assert store.get(created.id) is None
    assert store.delete(created.id) is False


def test_recent_topics_returns_latest_distinct(tmp_path):
    store = SessionStore(tmp_path / "s.db")
    for topic in ["A", "B", "A", "C"]:
        store.create(sample_content(topic=topic))
    assert store.recent_topics(limit=2) == ["C", "A"]
    assert store.recent_topics(limit=10) == ["C", "A", "B"]
