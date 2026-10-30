import random

from tests.conftest import admin_client

from app.db import Database
from app.main import create_app
from app.models import KoreanExample
from app.wiring import Services
from tests.conftest import NAMES, sample_draft, seed_expressions
from tests.test_api import FakeGenerator, InlineExecutor


def test_add_upserts_by_normalized_key_and_keeps_the_id(store):
    a = store.expressions.add("play the devil's advocate", "m", [], [], "n", None, "casual", "s")
    b = store.expressions.add("play devil's advocate", "m2", ["argue"], ["e"], "n2", "반론", "casual", "s")
    assert a == b and store.expressions.count() == 1
    assert store.expressions.get(a).meaning == "m2"
    assert store.expressions.get(a).synonyms == ["argue"]


def test_get_misses_and_list_all_runs_in_the_order_added(store):
    assert store.expressions.get(1) is None
    first = store.expressions.add("one", "m", [], [], "n", None, None, "s")
    second = store.expressions.add("two", "m", [], [], "n", None, "workplace", "s")
    assert [(e.id, e.setting) for e in store.expressions.list_all()] == [(first, None), (second, "workplace")]


def test_pick_prefers_untaught_and_mixes_settings(store):
    for r in ("casual", "workplace", None):
        for i in range(3):
            store.expressions.add(f"{r} {NAMES[i]}", "m", [], [], "n", None, r, "s")
    picked = store.expressions.pick(3, random.Random(1))
    assert {e.setting for e in picked} == {"casual", "workplace", None}


def test_pick_takes_untaught_before_any_taught_one(store):
    taught = store.expressions.add("old", "m", [], [], "n", None, None, "s")
    store.sessions.create(sample_draft(), [taught])
    fresh = [store.expressions.add(f"new {name}", "m", [], [], "n", None, None, "s") for name in NAMES[:2]]
    picked = [e.id for e in store.expressions.pick(3, random.Random(0))]
    assert sorted(picked[:2]) == fresh and picked[2] == taught


def test_pick_fills_from_the_longest_ago_taught_when_untaught_run_out(store):
    first = store.expressions.add("one", "m", [], [], "n", None, None, "s")
    second = store.expressions.add("two", "m", [], [], "n", None, None, "s")
    store.sessions.create(sample_draft(), [first])
    store.sessions.create(sample_draft(), [second])
    assert [e.id for e in store.expressions.pick(2, random.Random(0))] == [first, second]


def test_pick_returns_what_there_is(store):
    assert store.expressions.pick(5, random.Random(0)) == []


def test_list_all_carries_each_source_and_the_sessions_that_taught_it(store):
    taught = store.expressions.add("old", "m", [], ["e"], "n", "한", "casual", "https://www.youtube.com/post/x")
    fresh = store.expressions.add("new", "m", [], [], "n", None, None, "session")
    first = store.sessions.create(sample_draft(), [taught]).id
    second = store.sessions.create(sample_draft(), [taught]).id
    entries = {e.id: e for e in store.expressions.list_all()}
    assert entries[taught].source == "https://www.youtube.com/post/x" and entries[taught].sessions == [first, second]
    assert entries[fresh].sessions == [] and entries[fresh].added_at


def test_the_corpus_is_served_whole(tmp_path):
    db = Database(tmp_path / "s.db")
    db.expressions.add("touch base", "m", [], ["Let's touch base."], "n", "연락하다", "workplace", "session")
    with admin_client(create_app(db, Services(FakeGenerator()), InlineExecutor())) as c:
        [entry] = c.get("/api/expressions").json()
    assert (entry["phrase"], entry["setting"], entry["source"], entry["sessions"]) == ("touch base", "workplace", "session", [])


def test_delete_takes_an_expression_out_of_the_corpus_and_every_session_that_taught_it(store):
    kept, gone = seed_expressions(store, 2)
    session = store.sessions.create(sample_draft(), [kept, gone]).id
    store.sessions.set_stars(session, store.sessions.get_stars(session).model_copy(update={"expressions": [kept, gone]}))
    assert store.expressions.delete(gone) is True
    assert store.expressions.get(gone) is None and store.expressions.count() == 1
    assert [e.id for e in store.sessions.get(session).content.expressions] == [kept]
    assert store.sessions.get_stars(session).expressions == [kept]
    assert store.expressions.delete(gone) is False


def test_an_expression_is_deleted_over_http_once(tmp_path):
    db = Database(tmp_path / "s.db")
    [expression] = seed_expressions(db, 1)
    with admin_client(create_app(db, Services(FakeGenerator()), InlineExecutor())) as c:
        assert c.delete(f"/api/expressions/{expression}").status_code == 204
        assert c.delete(f"/api/expressions/{expression}").status_code == 404
        assert c.get("/api/expressions").json() == []


def test_a_korean_example_comes_with_its_expression_wherever_it_is_read(store):
    a, b = seed_expressions(store, 2)
    with store.connect() as conn:
        conn.execute("UPDATE expressions SET korean_example = ? WHERE id = ?",
                     ('{"korean": "못 오면 미리 알려 줘.", "english": "Let me know in advance if you can\'t come."}', a))
    session = store.sessions.create(sample_draft(), [a, b]).id
    example = KoreanExample(korean="못 오면 미리 알려 줘.", english="Let me know in advance if you can't come.")
    assert [e.korean_example for e in store.sessions.get(session).content.expressions] == [example, None]
    assert store.expressions.get(a).korean_example == example
    assert [e.korean_example for e in store.expressions.list_all()] == [example, None]
