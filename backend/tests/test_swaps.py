import random

from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.wiring import Services
from tests.conftest import add_user, admin_client, sample_draft, seed_expressions, sign_in
from tests.test_api import FakeGenerator, InlineExecutor


def taught(store, session_id: int) -> list[int]:
    return [e.id for e in store.sessions.get(session_id).content.expressions]


def test_a_swap_puts_a_fresh_expression_in_the_same_place(store):
    a, b, c = seed_expressions(store, 3)
    session = store.sessions.create(sample_draft(), [a, b]).id
    store.sessions.set_star(session, "expressions", a, True)
    store.sessions.set_star(session, "expressions", b, True)
    swapped_in = store.sessions.swap_expression(session, a)
    assert swapped_in is not None and swapped_in.id == c
    assert taught(store, session) == [c, b]
    assert store.sessions.get_stars(session).expressions == [b]


def test_a_swapped_out_expression_is_unused_again_and_keeps_no_record(store):
    a, b, c = seed_expressions(store, 3)
    session = store.sessions.create(sample_draft(), [a]).id
    store.sessions.swap_expression(session, a, random.Random(0))
    [swapped_in] = taught(store, session)
    entries = {e.id: e for e in store.expressions.list_all()}
    assert entries[a].sessions == [] and "swapped" not in entries[a].model_dump()
    assert entries[swapped_in].sessions == [session]
    assert set(e.id for e in store.expressions.pick(2, random.Random(0))) == {a, b, c} - {swapped_in}


def test_a_swap_never_brings_in_what_the_session_teaches(store):
    a, b, c, d = seed_expressions(store, 4)
    session = store.sessions.create(sample_draft(), [a, b]).id
    first = store.sessions.swap_expression(session, b)
    assert first.id in {c, d}
    second = store.sessions.swap_expression(session, first.id)
    assert second.id not in {a, first.id}
    assert taught(store, session) == [a, second.id]


def test_a_swap_misses_an_expression_the_session_does_not_teach(store):
    a, b = seed_expressions(store, 2)
    session = store.sessions.create(sample_draft(), [a]).id
    assert store.sessions.swap_expression(session, b) is None
    assert store.sessions.swap_expression(session + 1, a) is None


def test_an_expression_is_swapped_over_http(tmp_path):
    db = Database(tmp_path / "s.db")
    a, b = seed_expressions(db, 2)
    session = db.sessions.create(sample_draft(), [a]).id
    with admin_client(create_app(db, Services(FakeGenerator()), InlineExecutor())) as c:
        res = c.post(f"/api/sessions/{session}/expressions/{a}/swap")
        assert res.status_code == 200 and res.json()["id"] == b
        assert c.post(f"/api/sessions/{session}/expressions/{a}/swap").status_code == 404
        assert c.get(f"/api/sessions/{session}").json()["content"]["expressions"][0]["id"] == b


def test_an_added_expression_goes_last_and_is_never_one_the_session_teaches(store):
    a, b, c = seed_expressions(store, 3)
    session = store.sessions.create(sample_draft(), [a, b]).id
    added = store.sessions.add_expression(session)
    assert added is not None and added.id == c
    assert taught(store, session) == [a, b, c]
    assert store.sessions.add_expression(session) is None


def test_nothing_is_added_to_a_missing_session(store):
    seed_expressions(store, 1)
    assert store.sessions.add_expression(1) is None


def test_an_expression_is_added_over_http(tmp_path):
    db = Database(tmp_path / "s.db")
    a, b = seed_expressions(db, 2)
    session = db.sessions.create(sample_draft(), [a]).id
    with admin_client(create_app(db, Services(FakeGenerator()), InlineExecutor())) as c:
        res = c.post(f"/api/sessions/{session}/expressions")
        assert res.status_code == 200 and res.json()["id"] == b
        assert c.post(f"/api/sessions/{session}/expressions").status_code == 404
        assert c.post(f"/api/sessions/{session + 1}/expressions").status_code == 404
        assert [e["id"] for e in c.get(f"/api/sessions/{session}").json()["content"]["expressions"]] == [a, b]


def test_a_swap_and_an_add_avoid_what_the_one_asking_saw(tmp_path):
    db = Database(tmp_path / "s.db")
    a, b, c, d = seed_expressions(db, 4)
    me, other = add_user(db, "me@example.com"), add_user(db, "other@example.com")
    db.sessions.create(sample_draft(), [b, d], created_by=me.id)
    shared = db.sessions.create(sample_draft(), [a], created_by=other.id)
    db.shares.share(shared.id, me.id)
    client = TestClient(create_app(db, Services(FakeGenerator()), InlineExecutor()))
    sign_in(client, db, me)
    assert client.post(f"/api/sessions/{shared.id}/expressions/{a}/swap").json()["id"] == c
    # a went out of this session, so no session of mine uses it any more: it is new to me again.
    assert client.post(f"/api/sessions/{shared.id}/expressions").json()["id"] == a
