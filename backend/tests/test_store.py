import pytest

from app.generation.generator import VOCABULARY_COUNT
from app.models import Correction, Note, Stars, SummaryFeedback, SummaryFix
from app.pictures.scenes import Scene
from tests.conftest import sample_draft, seed_expressions


def test_create_then_get_roundtrip(store, draft):
    created = store.sessions.create(draft, [])
    fetched = store.sessions.get(created.id)
    assert fetched == created
    assert fetched.topic == "Digital twins"
    article = fetched.content.article
    assert (article.title, article.questions, article.sources, article.translation) == (
        draft.article.title, draft.article.questions, draft.article.sources, draft.article.translation
    )
    assert [v.model_dump(exclude={"id", "image", "example_image"}) for v in fetched.content.vocabulary] == [
        v.model_dump() for v in draft.vocabulary
    ]


def test_create_splits_paragraphs_links_expressions_in_order_and_get_puts_it_back(store):
    ids = seed_expressions(store, 5)
    session = store.sessions.create(sample_draft(), ids[::-1])
    got = store.sessions.get(session.id)
    assert [p.text for p in got.content.article.paragraphs] == ["One.", "Two two.", "Three."]
    assert [e.id for e in got.content.expressions] == ids[::-1]
    assert got.content.expressions[0].phrase == "echo phrase"
    assert [v.word for v in got.content.vocabulary] == [f"word{i}" for i in range(VOCABULARY_COUNT)]
    assert got.content.vocabulary[0].image is None


def test_list_returns_newest_first_with_title(store):
    first = store.sessions.create(sample_draft(topic="A", title="First"), [])
    second = store.sessions.create(sample_draft(topic="B", title="Second"), [])
    summaries = store.sessions.list_all()
    assert [s.id for s in summaries] == [second.id, first.id]
    assert (summaries[0].title, summaries[0].topic) == ("Second", "B")


def test_get_missing_returns_none(store):
    assert store.sessions.get(999) is None
    assert not store.sessions.exists(999)


def test_delete_removes_session(store, draft):
    created = store.sessions.create(draft, [])
    assert store.sessions.delete(created.id) == []
    assert store.sessions.get(created.id) is None
    assert store.sessions.delete(created.id) is None


def test_delete_cascades_and_hands_back_the_picture_ids(store):
    session = store.sessions.create(sample_draft(), seed_expressions(store, 2))
    p = store.pictures.add("m", 1, None)
    store.sessions.replace_picture(session.content.vocabulary[0].id, "example_image", p)
    assert store.sessions.delete(session.id) == [p]
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM session_expressions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM expressions").fetchone()[0] == 2  # the corpus stays
    assert store.sessions.delete(session.id) is None


def test_recent_topics_returns_latest_distinct(store):
    for topic in ["A", "B", "A", "C"]:
        store.sessions.create(sample_draft(topic=topic), [])
    assert store.sessions.recent_topics(limit=2) == ["C", "A"]
    assert store.sessions.recent_topics(limit=10) == ["C", "A", "B"]


def test_used_words_lists_distinct_words_newest_first(store):
    older = sample_draft()
    older.vocabulary[0] = older.vocabulary[0].model_copy(update={"word": "older"})
    store.sessions.create(older, [])
    store.sessions.create(sample_draft(), [])
    assert store.sessions.used_words() == tuple(f"word{i}" for i in range(VOCABULARY_COUNT)) + ("older",)
    assert store.sessions.used_words(limit_sessions=1) == tuple(f"word{i}" for i in range(VOCABULARY_COUNT))


def test_used_words_is_empty_on_fresh_store(store):
    assert store.sessions.used_words() == ()


def test_stars_are_ids_and_ignore_ids_from_other_sessions(store):
    ids = seed_expressions(store, 3)
    session = store.sessions.create(sample_draft(), ids[:2])
    other = store.sessions.create(sample_draft(), ids[2:])
    words = [v.id for v in session.content.vocabulary]
    assert store.sessions.get_stars(session.id) == Stars()

    foreign = other.content.vocabulary[0].id
    saved = store.sessions.set_stars(session.id, Stars(expressions=[ids[1], ids[1], ids[2]], words=[words[3], foreign]))
    assert saved == Stars(expressions=[ids[1]], words=[words[3]])

    store.sessions.set_stars(session.id, Stars(words=[words[5]]))
    assert store.sessions.get_stars(session.id) == Stars(expressions=[], words=[words[5]])
    assert store.sessions.get_stars(other.id) == Stars()

    store.sessions.delete(session.id)
    assert store.sessions.get_stars(session.id) == Stars()


def test_a_note_is_rewritten_whole_and_goes_with_the_session(store, draft):
    session = store.sessions.create(draft, [])
    assert store.sessions.get_note(session.id) == Note(text="")

    store.sessions.set_note(session.id, Note(text="hedge: stress on first syllable"))
    saved = store.sessions.set_note(session.id, Note(text="line one\nline two"))
    assert saved == Note(text="line one\nline two")
    assert store.sessions.get_note(session.id) == Note(text="line one\nline two")

    store.sessions.delete(session.id)
    assert store.sessions.get_note(session.id) == Note(text="")


def test_replace_picture_returns_the_old_one_and_can_change_the_scene(store):
    session = store.sessions.create(sample_draft(), [])
    word = session.content.vocabulary[1]
    p1, p2 = store.pictures.add("m", 1, None), store.pictures.add("m", 1, None)
    assert store.sessions.replace_picture(word.id, "image", p1) is None
    assert store.sessions.replace_picture(word.id, "image", p2, Scene("new", "cap")) == p1
    again = store.sessions.get(session.id).content.vocabulary[1]
    assert (again.image, again.scene, again.caption) == (f"{p2}.png", "new", "cap")
    with pytest.raises(KeyError):
        store.sessions.replace_picture(999, "image", p1)


def test_a_picture_landing_on_a_word_keeps_what_landed_on_it_meanwhile(store):
    session = store.sessions.create(sample_draft(), [])
    word = session.content.vocabulary[1]
    scene, example = store.pictures.add("m", 1, None), store.pictures.add("m", 1, None)
    store.sessions.replace_picture(word.id, "image", scene)
    store.sessions.replace_picture(word.id, "example_image", example)
    got = store.sessions.get(session.id).content.vocabulary[1]
    assert (got.image, got.example_image, got.scene) == (f"{scene}.png", f"{example}.png", "scene 1")


def test_paragraphs_know_their_session(store):
    session = store.sessions.create(sample_draft(), [])
    assert store.sessions.session_of_paragraph(session.content.article.paragraphs[2].id) == session.id
    assert store.sessions.session_of_paragraph(999) is None
    assert not hasattr(store.sessions, "session_of_vocabulary")  # nothing asks it


def test_examples_point_at_an_expression_or_a_word_of_the_session(store):
    session = store.sessions.create(sample_draft(), seed_expressions(store, 1))
    other = store.sessions.create(sample_draft(), [])
    e, w = session.content.expressions[0], session.content.vocabulary[0]
    ex = store.records.add_example(session.id, e.id, None, "I said", "Coach said", 4)
    wx = store.records.add_example(session.id, None, w.id, "word use", "echo", 2)
    assert (ex.expression_id, ex.vocabulary_id, ex.user_text, ex.seconds) == (e.id, None, "I said", 4)
    assert [(x.id, x.expression_id, x.vocabulary_id) for x in store.records.list_examples(session.id)] == [(ex.id, e.id, None), (wx.id, None, w.id)]
    with pytest.raises(KeyError):
        store.records.add_example(session.id, 999, None, "x", "y", 0)
    with pytest.raises(KeyError):
        store.records.add_example(other.id, e.id, None, "x", "y", 0)  # not taught in that session
    with pytest.raises(KeyError):
        store.records.add_example(session.id, None, other.content.vocabulary[0].id, "x", "y", 0)
    assert store.records.list_examples(other.id) == []
    assert store.sessions.delete(session.id) is not None
    assert store.records.list_examples(session.id) == []


def test_readings_and_summaries_hang_off_a_paragraph_and_go_with_the_session(store):
    session = store.sessions.create(sample_draft(), [])
    other = store.sessions.create(sample_draft(), [])
    first, second = (p.id for p in session.content.article.paragraphs[:2])
    r1 = store.records.add_reading(first, "one", 3, [])
    r2 = store.records.add_reading(second, "two two", 4, [Correction(word="two", heard="tu", fix="tuː", at=1)])
    readings = store.records.list_readings(session.id)
    assert [(r.id, r.paragraph_id) for r in readings] == [(r2.id, second), (r1.id, first)]  # newest first
    assert readings[0].corrections[0].at == 1 and readings[1].corrections == []

    feedback = SummaryFeedback(missed=[], fixes=[SummaryFix(said="a", better="b")], summary="s")
    s1 = store.records.add_summary(second, "said", feedback, 5)
    s2 = store.records.add_summary(first, "said again", feedback, 6)
    summaries = store.records.list_summaries(session.id)
    assert [(s.id, s.paragraph_id) for s in summaries] == [(s1.id, second), (s2.id, first)]  # in the order made
    assert summaries[0].feedback == feedback

    assert store.records.list_readings(other.id) == [] and store.records.list_summaries(other.id) == []
    store.sessions.delete(session.id)
    assert store.records.list_readings(session.id) == [] and store.records.list_summaries(session.id) == []


def test_a_reading_kept_before_corrections_were_saved_has_none(store):
    session = store.sessions.create(sample_draft(), [])
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO readings (created_at, paragraph_id, user_text) VALUES ('2026-09-01T00:00:00+00:00', ?, 'old')",
            (session.content.article.paragraphs[0].id,),
        )
    [reading] = store.records.list_readings(session.id)
    assert reading.corrections is None
