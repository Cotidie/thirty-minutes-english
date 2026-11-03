import re
import unicodedata

import pytest

from app.accounts.passwords import hash_password, verify_password
from app.db.accounts import SEARCH_LIMIT, EmailTaken, UsernameTaken
from tests.conftest import add_user, sample_draft


def test_a_password_is_kept_only_as_a_hash_and_checks_out():
    stored = hash_password("correct horse")
    assert "correct horse" not in stored and stored.startswith("scrypt$")
    assert verify_password("correct horse", stored) and not verify_password("wrong", stored)


def test_a_stored_value_that_is_not_a_hash_never_checks_out():
    assert not verify_password("anything", "not a hash")


def test_an_email_differing_only_in_case_or_spaces_is_the_same_account(store):
    store.accounts.create("  Mina@Example.COM ", "h")
    assert store.accounts.by_email("mina@example.com").email == "mina@example.com"
    assert store.accounts.by_email(" MINA@example.com").email == "mina@example.com"
    with pytest.raises(EmailTaken):
        store.accounts.create("mina@example.com", "h")


def test_a_new_account_has_no_rights(store):
    user = store.accounts.create("a@example.com", "h")
    assert user.is_admin is False
    assert store.accounts.with_hash("a@example.com") == (user, "h")
    assert store.accounts.with_hash("b@example.com") is None


def test_a_login_token_is_stored_hashed_and_ends(store):
    user = store.accounts.create("a@example.com", "h")
    token = store.accounts.start_login(user.id)
    assert store.accounts.user_of_login(token).id == user.id
    with store.connect() as conn:
        assert token not in [r[0] for r in conn.execute("SELECT token_hash FROM logins")]
    store.accounts.end_login(token)
    assert store.accounts.user_of_login(token) is None
    assert store.accounts.user_of_login("") is None


def test_an_expired_login_is_refused_and_purged_at_the_next_login(store):
    user = store.accounts.create("a@example.com", "h")
    token = store.accounts.start_login(user.id)
    with store.connect() as conn:
        conn.execute("UPDATE logins SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert store.accounts.user_of_login(token) is None
    store.accounts.start_login(user.id)
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM logins").fetchone()[0] == 1


def test_a_new_password_ends_every_login(store):
    user = store.accounts.create("a@example.com", "h")
    token = store.accounts.start_login(user.id)
    store.accounts.set_password(user.id, "new")
    assert store.accounts.with_hash("a@example.com")[1] == "new"
    assert store.accounts.user_of_login(token) is None


def test_an_account_keeps_the_name_it_chose_and_one_made_without_a_name_gets_a_random_one(store):
    assert store.accounts.create("a@example.com", "h", "미나").username == "미나"
    first, second = (store.accounts.create(f"{n}@example.com", "h").username for n in ("b", "c"))
    assert first != second and all(re.fullmatch(r"user_[0-9a-f]{6}", name) for name in (first, second))


def test_a_name_is_taken_whatever_its_case_or_how_its_korean_was_typed(store):
    store.accounts.create("a@example.com", "h", "Mina")
    with pytest.raises(UsernameTaken):
        store.accounts.create("b@example.com", "h", "mina")
    store.accounts.create("c@example.com", "h", "한글")
    with pytest.raises(UsernameTaken):
        store.accounts.create("d@example.com", "h", unicodedata.normalize("NFD", "한글"))


def test_an_email_in_use_is_named_first_when_the_name_is_in_use_too(store):
    store.accounts.create("a@example.com", "h", "mina")
    with pytest.raises(EmailTaken):
        store.accounts.create("a@example.com", "h", "mina")


def test_a_new_name_is_kept_and_recasing_ones_own_name_is_no_clash(store):
    me = store.accounts.create("a@example.com", "h", "mina")
    store.accounts.create("b@example.com", "h", "jo")
    assert store.accounts.set_username(me.id, "Mina").username == "Mina"
    with pytest.raises(UsernameTaken):
        store.accounts.set_username(me.id, "JO")
    assert store.accounts.get(me.id).username == "Mina"


def test_a_search_finds_names_containing_the_text_starts_first_and_leaves_out_who_searches(store):
    me = store.accounts.create("me@example.com", "h", "mina_me")
    for name in ("jomina", "Mina", "minsu", "sumin"):
        store.accounts.create(f"{name}@example.com", "h", name)
    assert [u.username for u in store.accounts.search("MIN", excluding=me.id)] == ["Mina", "minsu", "jomina", "sumin"]
    assert [u.username for u in store.accounts.search("  ", excluding=me.id)] == []


def test_a_search_reads_percent_and_underscore_as_themselves(store):
    me = store.accounts.create("me@example.com", "h", "me")
    for name in ("a_b", "axb"):
        store.accounts.create(f"{name}@example.com", "h", name)
    assert [u.username for u in store.accounts.search("a_", excluding=me.id)] == ["a_b"]
    assert store.accounts.search("%", excluding=me.id) == []


def test_a_search_stops_at_the_limit(store):
    me = store.accounts.create("me@example.com", "h", "me")
    for i in range(12):
        store.accounts.create(f"u{i}@example.com", "h", f"kim{i:02}")
    assert len(store.accounts.search("kim", excluding=me.id)) == SEARCH_LIMIT


def test_ensure_admin_claims_old_sessions_once_and_then_does_nothing(store):
    old = store.sessions.create(sample_draft(), [])
    admin = store.accounts.ensure_admin("boss@example.com", "h")
    assert admin.is_admin and store.shares.created_by(old.id) == admin.id
    assert store.accounts.ensure_admin("other@example.com", "h") is None
    assert store.accounts.by_email("other@example.com") is None


def test_ensure_admin_takes_over_an_account_with_that_email_and_ends_its_logins(store):
    user = store.accounts.create("boss@example.com", "old")
    token = store.accounts.start_login(user.id)
    admin = store.accounts.ensure_admin("boss@example.com", "new")
    assert admin.id == user.id and store.accounts.with_hash("boss@example.com")[1] == "new"
    assert store.accounts.user_of_login(token) is None


def test_ensure_admin_leaves_a_session_someone_already_made_alone(store):
    me = add_user(store, "me@example.com")
    mine = store.sessions.create(sample_draft(), [], created_by=me.id)
    store.accounts.ensure_admin("boss@example.com", "h")
    assert store.shares.created_by(mine.id) == me.id


def test_access_goes_to_the_creator_the_shared_and_the_admin_only(store):
    me, friend, stranger = (add_user(store, f"{n}@example.com") for n in ("me", "friend", "stranger"))
    admin = add_user(store, "boss@example.com", admin=True)
    session = store.sessions.create(sample_draft(), [], created_by=me.id)
    store.shares.share(session.id, friend.id)
    assert [store.shares.can_access(u, session.id) for u in (me, friend, stranger, admin)] == [True, True, False, True]
    assert not store.shares.can_access(me, 999) and not store.shares.can_access(admin, 999)


def test_nobody_but_the_admin_can_open_a_session_with_no_creator(store):
    me = add_user(store, "me@example.com")
    admin = add_user(store, "boss@example.com", admin=True)
    session = store.sessions.create(sample_draft(), [])
    assert not store.shares.can_access(me, session.id) and store.shares.can_access(admin, session.id)


def test_sharing_twice_lists_once_and_unsharing_says_whether_there_was_a_share(store):
    me, friend = add_user(store, "me@example.com"), add_user(store, "friend@example.com")
    session = store.sessions.create(sample_draft(), [], created_by=me.id)
    store.shares.share(session.id, friend.id)
    store.shares.share(session.id, friend.id)
    assert store.shares.shared_with(session.id) == [friend]
    assert store.shares.unshare(session.id, friend.id) is True
    assert store.shares.unshare(session.id, friend.id) is False
    assert not store.shares.can_access(friend, session.id)


def test_a_picture_is_seen_only_through_a_session_one_can_open(store):
    me, stranger = add_user(store, "me@example.com"), add_user(store, "stranger@example.com")
    session = store.sessions.create(sample_draft(), [], created_by=me.id)
    word = session.content.vocabulary[0]
    drawn, example, cover = (store.pictures.add(None, None, None) for _ in range(3))
    store.sessions.replace_picture(word.id, "image", drawn)
    store.sessions.replace_picture(word.id, "example_image", example)
    store.sessions.add_figure(session.id, None, cover, "c", None, None)
    for picture in (drawn, example, cover):
        assert store.shares.can_see_picture(me, picture) and not store.shares.can_see_picture(stranger, picture)
    assert not store.shares.can_see_picture(me, store.pictures.add(None, None, None))  # no session shows it
