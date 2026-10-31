import threading

from app.credits import PRICES
from app.live.changes import AccountChange
from tests.conftest import add_user


def test_a_new_account_has_nothing_and_a_grant_shows_up_first(store):
    mina = add_user(store, "mina@example.com")
    admin = add_user(store, "boss@example.com", admin=True)
    assert store.credits.balance(mina.id) == 0 and store.credits.recent(mina.id) == []
    store.credits.grant(mina.id, 500, by=admin.id)
    assert store.credits.balance(mina.id) == 500
    (entry,) = store.credits.recent(mina.id)
    assert (entry.amount, entry.kind, entry.detail) == (500, "grant", None)


def test_a_charge_takes_the_price_and_names_what_it_was_for(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 15, by=mina.id)
    assert store.credits.charge(mina, "redraw", "sprawl") is True
    assert store.credits.balance(mina.id) == 5
    assert [(e.amount, e.kind, e.detail) for e in store.credits.recent(mina.id)] == [(-10, "redraw", "sprawl"), (15, "grant", None)]


def test_a_charge_the_balance_cannot_cover_leaves_no_row(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 3, by=mina.id)
    assert store.credits.charge(mina, "redraw") is False
    assert store.credits.balance(mina.id) == 3 and len(store.credits.recent(mina.id)) == 1


def test_the_admin_is_never_charged_and_nothing_is_written(store):
    boss = add_user(store, "boss@example.com", admin=True)
    assert store.credits.charge(boss, "session", "Trams") is True
    assert store.credits.recent(boss.id) == []


def test_a_refund_is_a_positive_row_of_its_own_kind(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 200, by=mina.id)
    store.credits.charge(mina, "session", "Trams")
    store.credits.refund(mina.id, PRICES["session"], "Trams")
    assert store.credits.balance(mina.id) == 200
    assert store.credits.recent(mina.id)[0].kind == "refund"


def test_recent_is_newest_first_and_stops_at_the_limit(store):
    mina = add_user(store, "mina@example.com")
    for amount in range(1, 13):
        store.credits.grant(mina.id, amount, by=mina.id)
    assert [e.amount for e in store.credits.recent(mina.id)] == list(range(12, 2, -1))
    assert len(store.credits.recent(mina.id, limit=3)) == 3


def test_two_charges_at_once_on_one_price_worth_of_balance_let_only_one_through(store):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, 10, by=mina.id)
    results: list[bool] = []
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        results.append(store.credits.charge(mina, "redraw"))

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False, True]
    assert store.credits.balance(mina.id) == 0


def test_every_row_tells_the_account_to_read_its_credits_again(store, recorder):
    mina = add_user(store, "mina@example.com")
    boss = add_user(store, "boss@example.com", admin=True)
    store.credits.grant(mina.id, 10, by=boss.id)
    store.credits.charge(mina, "speech", "It was flawed.")
    store.credits.refund(mina.id, 1, None)
    store.credits.charge(boss, "speech")
    assert recorder.published == [(mina.id, AccountChange.CREDITS)] * 3
