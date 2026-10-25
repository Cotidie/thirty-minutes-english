import random

from tests.conftest import NAMES, sample_draft


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
