import pytest
from fastapi.testclient import TestClient

from app.accounts.admin import ensure_admin_from
from app.accounts.passwords import hash_password, verify_password
from app.accounts.reset_password import main as reset_password
from app.db import Database
from app.main import create_app
from app.wiring import Services
from tests.conftest import add_user, sample_draft, sign_in
from tests.test_api import FakeGenerator, InlineExecutor

GOOD = {"ADMIN_EMAIL": "Boss@Example.com", "ADMIN_PASSWORD": "12345678"}


def test_the_env_creates_the_admin_who_can_log_in(store):
    ensure_admin_from(store, GOOD)
    user, stored = store.accounts.with_hash("boss@example.com")
    assert user.is_admin and verify_password("12345678", stored)


@pytest.mark.parametrize(
    "env",
    [{}, {"ADMIN_EMAIL": "boss@example.com"}, {"ADMIN_PASSWORD": "12345678"}, {"ADMIN_EMAIL": "boss@example.com", "ADMIN_PASSWORD": "short"}, {"ADMIN_EMAIL": "not-an-email", "ADMIN_PASSWORD": "12345678"}],
)
def test_without_usable_values_the_app_warns_and_old_sessions_stay_hidden_until_they_come(store, caplog, env):
    old = store.sessions.create(sample_draft(), [])
    ensure_admin_from(store, env)
    assert "ADMIN_EMAIL" in caplog.text and store.accounts.list_all() == []
    assert store.shares.created_by(old.id) is None
    ensure_admin_from(store, GOOD)
    assert store.shares.created_by(old.id) == store.accounts.by_email("boss@example.com").id


def test_once_there_is_an_admin_a_new_email_in_the_env_is_ignored(store, caplog):
    ensure_admin_from(store, GOOD)
    ensure_admin_from(store, {"ADMIN_EMAIL": "other@example.com"})
    ensure_admin_from(store, {})
    assert store.accounts.by_email("other@example.com") is None
    assert verify_password("12345678", store.accounts.with_hash("boss@example.com")[1])
    assert "ADMIN_EMAIL" not in caplog.text


def test_a_new_password_in_the_env_becomes_the_admins_and_ends_its_logins(store):
    ensure_admin_from(store, GOOD)
    admin = store.accounts.by_email("boss@example.com")
    token = store.accounts.start_login(admin.id)
    ensure_admin_from(store, {"ADMIN_PASSWORD": "a-new-password"})
    stored = store.accounts.with_hash("boss@example.com")[1]
    assert verify_password("a-new-password", stored) and not verify_password("12345678", stored)
    assert store.accounts.user_of_login(token) is None


def test_the_same_password_in_the_env_keeps_the_admin_logged_in(store):
    ensure_admin_from(store, GOOD)
    admin = store.accounts.by_email("boss@example.com")
    token = store.accounts.start_login(admin.id)
    ensure_admin_from(store, GOOD)
    assert store.accounts.user_of_login(token).id == admin.id


def test_a_blank_password_in_the_env_leaves_the_admin_alone(store, caplog):
    ensure_admin_from(store, GOOD)
    ensure_admin_from(store, {"ADMIN_EMAIL": "boss@example.com", "ADMIN_PASSWORD": ""})
    assert verify_password("12345678", store.accounts.with_hash("boss@example.com")[1])
    assert "ADMIN_PASSWORD" not in caplog.text


def test_a_short_password_in_the_env_is_refused_with_a_warning(store, caplog):
    ensure_admin_from(store, GOOD)
    ensure_admin_from(store, {"ADMIN_PASSWORD": "short"})
    assert verify_password("12345678", store.accounts.with_hash("boss@example.com")[1])
    assert "ADMIN_PASSWORD" in caplog.text


def test_the_env_password_never_touches_anyone_but_the_admin(store):
    ensure_admin_from(store, GOOD)
    other = store.accounts.create("a@example.com", hash_password("their-password"))
    ensure_admin_from(store, {"ADMIN_PASSWORD": "a-new-password"})
    assert verify_password("their-password", store.accounts.with_hash(other.email)[1])


def test_reset_prints_a_new_password_once_and_ends_the_logins(tmp_path, capsys, monkeypatch):
    path = tmp_path / "s.db"
    monkeypatch.setenv("DB_PATH", str(path))
    db = Database(path)
    user = db.accounts.create("a@example.com", hash_password("old-password"))
    token = db.accounts.start_login(user.id)
    assert reset_password([" A@Example.com "]) == 0
    printed = capsys.readouterr().out.strip().split()[-1]
    assert len(printed) >= 16 and verify_password(printed, db.accounts.with_hash("a@example.com")[1])
    assert db.accounts.user_of_login(token) is None


def test_reset_of_an_unknown_email_exits_1_and_without_one_exits_2(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "s.db"))
    assert reset_password(["nobody@example.com"]) == 1
    assert "nobody@example.com" in capsys.readouterr().err
    assert reset_password([]) == 2


@pytest.fixture
def accounts(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    admin, user = add_user(db, "boss@example.com", admin=True), add_user(db, "a@example.com")
    admin_c, user_c = TestClient(app), TestClient(app)
    sign_in(admin_c, db, admin)
    sign_in(user_c, db, user)
    return admin_c, user_c, user


def test_the_admin_lists_accounts_and_turns_creation_on_and_off(accounts):
    admin, user_client, user = accounts
    assert [a["email"] for a in admin.get("/api/accounts").json()] == ["boss@example.com", "a@example.com"]
    assert "password_hash" not in admin.get("/api/accounts").json()[0]
    assert admin.put(f"/api/accounts/{user.id}", json={"can_create": True}).json()["can_create"] is True
    assert user_client.get("/api/auth/me").json()["can_create"] is True
    assert user_client.post("/api/sessions", json={"topic": "X"}).status_code == 202
    assert admin.put(f"/api/accounts/{user.id}", json={"can_create": False}).json()["can_create"] is False
    assert user_client.post("/api/sessions", json={"topic": "X"}).status_code == 403


def test_a_change_to_an_account_that_is_not_there_is_a_404(accounts):
    assert accounts[0].put("/api/accounts/999", json={"can_create": True}).status_code == 404


def test_others_cannot_see_or_change_accounts(accounts):
    _, user_client, user = accounts
    assert user_client.get("/api/accounts").status_code == 403
    assert user_client.put(f"/api/accounts/{user.id}", json={"can_create": True}).status_code == 403
