import pytest

from app.db import Database
from app.generation.generator import EXPRESSION_COUNT, VOCABULARY_COUNT
from app.models import PhraseCard, Stars
from tests.conftest import sample_content


@pytest.fixture
def store(tmp_path) -> Database:
    return Database(tmp_path / "s.db")


def test_create_then_get_roundtrip(tmp_path, content):
    store = Database(tmp_path / "s.db")
    created = store.sessions.create(content)
    fetched = store.sessions.get(created.id)
    assert fetched is not None
    assert fetched.topic == "Digital twins"
    assert fetched.content == content
    assert fetched.created_at == created.created_at


def test_list_returns_newest_first_with_title(tmp_path):
    store = Database(tmp_path / "s.db")
    first = store.sessions.create(sample_content(topic="A", title="First"))
    second = store.sessions.create(sample_content(topic="B", title="Second"))
    summaries = store.sessions.list_all()
    assert [s.id for s in summaries] == [second.id, first.id]
    assert summaries[0].title == "Second"
    assert summaries[0].topic == "B"


def test_get_missing_returns_none(tmp_path):
    store = Database(tmp_path / "s.db")
    assert store.sessions.get(999) is None


def test_delete_removes_session(tmp_path, content):
    store = Database(tmp_path / "s.db")
    created = store.sessions.create(content)
    assert store.sessions.delete(created.id) is True
    assert store.sessions.get(created.id) is None
    assert store.sessions.delete(created.id) is False


def test_recent_topics_returns_latest_distinct(tmp_path):
    store = Database(tmp_path / "s.db")
    for topic in ["A", "B", "A", "C"]:
        store.sessions.create(sample_content(topic=topic))
    assert store.sessions.recent_topics(limit=2) == ["C", "A"]
    assert store.sessions.recent_topics(limit=10) == ["C", "A", "B"]


def test_used_items_collects_distinct_phrases_and_words_newest_first(tmp_path):
    store = Database(tmp_path / "s.db")
    store.sessions.create(sample_content(topic="A"))
    store.sessions.create(sample_content(topic="B"))
    used = store.sessions.used_items()
    assert used.expressions == tuple(f"phrase {i}" for i in range(EXPRESSION_COUNT))
    assert used.words == tuple(f"word{i}" for i in range(VOCABULARY_COUNT))


def test_used_items_is_empty_on_fresh_store(tmp_path):
    assert not Database(tmp_path / "s.db").sessions.used_items()


def test_asks_round_trip_newest_first(store, content):
    session = store.sessions.create(content)
    store.records.add_ask(session.id, "눈치 좀 챙겨", "Read the room.", 12.5)
    store.records.add_ask(None, "I have much work", "I'm swamped.", 9)

    everything = store.records.list_asks()
    assert [a.user_text for a in everything] == ["I have much work", "눈치 좀 챙겨"]
    assert everything[0].session_id is None
    assert everything[1].seconds == 12.5
    assert [a.user_text for a in store.records.list_asks(session.id)] == ["눈치 좀 챙겨"]


def test_cards_are_stored_per_ask(store):
    ask = store.records.add_ask(None, "눈치 좀 챙겨", "Read the room.", 12)
    assert store.records.list_asks()[0].card is None

    store.records.set_ask_card(ask.id, PhraseCard(asked="눈치 좀 챙겨", english="Read the room.", note="friends or coworkers"))
    saved = store.records.list_asks()[0].card
    assert saved is not None and saved.english == "Read the room."
    assert saved.alternatives == []


def test_deleting_a_session_takes_its_asks(store, content):
    session = store.sessions.create(content)
    store.records.add_ask(session.id, "q", "a", 1)
    store.records.add_ask(None, "loose", "a", 1)

    store.sessions.delete(session.id)
    assert [a.user_text for a in store.records.list_asks()] == ["loose"]


def test_stars_replace_as_a_set_and_go_with_the_session(store):
    session = store.sessions.create(sample_content())
    assert store.sessions.get_stars(session.id).expressions == []

    saved = store.sessions.set_stars(session.id, Stars(expressions=["a moving target", "a moving target"], words=["mitigate"]))
    assert saved == Stars(expressions=["a moving target"], words=["mitigate"])

    store.sessions.set_stars(session.id, Stars(words=["ubiquitous"]))
    assert store.sessions.get_stars(session.id) == Stars(expressions=[], words=["ubiquitous"])

    store.sessions.delete(session.id)
    assert store.sessions.get_stars(session.id) == Stars()


def test_replacing_one_word_keeps_what_another_redraw_stored_meanwhile(store):
    session = store.sessions.create(sample_content())
    first = session.content.vocabulary[1].model_copy(update={"image": "1-new.png"})
    second = session.content.vocabulary[4].model_copy(update={"image": "4-new.png", "korean": "넷"})
    assert store.sessions.replace_vocabulary_item(session.id, 1, first).image is None
    assert store.sessions.replace_vocabulary_item(session.id, 4, second).word == "word4"
    words = store.sessions.get(session.id).content.vocabulary
    assert (words[1].image, words[4].image, words[4].korean) == ("1-new.png", "4-new.png", "넷")
    assert store.sessions.replace_vocabulary_item(session.id, 99, first) is None
    assert store.sessions.replace_vocabulary_item(999, 1, first) is None
