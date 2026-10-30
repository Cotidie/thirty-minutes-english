import re

import pytest
from fastapi.testclient import TestClient

from app.accounts.limits import FailedLogins, SignupLimit
from app.db import Database
from app.main import create_app
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor


@pytest.fixture
def client(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), InlineExecutor())
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def sign_up(client, email="a@example.com", password="12345678"):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def log_in(client, email="a@example.com", password="12345678"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_signing_up_logs_you_in_without_rights(client):
    res = sign_up(client, " Mina@Example.COM ")
    assert res.status_code == 201 and res.json()["email"] == "mina@example.com"
    assert res.json()["can_create"] is False and res.json()["is_admin"] is False
    cookie = res.headers["set-cookie"].lower()
    for part in ("login=", "httponly", "samesite=lax", "secure", "max-age=2592000", "path=/"):
        assert part in cookie
    assert client.get("/api/auth/me").json()["email"] == "mina@example.com"


@pytest.mark.parametrize(
    "email,password",
    [("not-an-email", "12345678"), ("a@b", "12345678"), ("a b@example.com", "12345678"), ("a@example.com", "1234567"), ("a@example.com", "x" * 1025)],
)
def test_a_bad_signup_gets_a_400_with_a_readable_reason(client, email, password):
    res = sign_up(client, email, password)
    assert res.status_code == 400 and isinstance(res.json()["detail"], str)
    assert client.get("/api/auth/me").status_code == 401


def test_an_email_in_use_gets_a_409(client):
    sign_up(client)
    res = sign_up(client, "A@EXAMPLE.COM")
    assert res.status_code == 409 and res.json()["detail"] == "An account already uses that email."


def test_a_login_works_however_the_email_is_cased(client):
    sign_up(client)
    client.cookies.clear()
    res = log_in(client, "  A@Example.com ")
    assert res.status_code == 200 and res.json()["email"] == "a@example.com"
    assert client.get("/api/auth/me").status_code == 200


def test_a_wrong_password_and_an_unknown_email_answer_alike(client):
    sign_up(client)
    client.cookies.clear()
    wrong = log_in(client, password="nope-nope")
    unknown = log_in(client, "b@example.com", "nope-nope")
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
    assert wrong.json()["detail"] == "That email and password don't match. Check them and try again."
    assert "set-cookie" not in wrong.headers


def test_the_eleventh_try_within_15_minutes_gets_a_429_even_with_the_right_password(client):
    sign_up(client)
    client.cookies.clear()
    for _ in range(10):
        assert log_in(client, password="nope-nope").status_code == 401
    res = log_in(client)
    assert res.status_code == 429 and res.json()["detail"] == "Too many tries. Wait 15 minutes and try again."
    assert log_in(client, "other@example.com", "nope-nope").status_code == 401  # only that email is held


def test_a_right_password_clears_the_failures(client):
    sign_up(client)
    client.cookies.clear()
    for _ in range(9):
        log_in(client, password="nope-nope")
    assert log_in(client).status_code == 200
    for _ in range(9):
        assert log_in(client, password="nope-nope").status_code == 401


def test_the_21st_signup_in_an_hour_gets_a_429(client):
    for i in range(20):
        assert sign_up(client, f"u{i}@example.com").status_code == 201
    res = sign_up(client, "u20@example.com")
    assert res.status_code == 429 and client.app.state.db.accounts.by_email("u20@example.com") is None


def test_logging_out_ends_the_login_on_the_server(client):
    sign_up(client)
    token = client.cookies["login"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("login", token)
    assert client.get("/api/auth/me").status_code == 401


def test_cookie_secure_can_be_turned_off_for_plain_http_development(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), InlineExecutor(), env={"COOKIE_SECURE": "false"})
    with TestClient(app) as c:
        res = sign_up(c)
    assert "secure" not in res.headers["set-cookie"].lower()


def test_every_route_but_signup_and_login_refuses_an_anonymous_call(client):
    public = {("POST", "/api/auth/signup"), ("POST", "/api/auth/login")}
    checked = 0
    for path, operations in client.app.openapi()["paths"].items():
        for method in operations:
            if (method.upper(), path) in public:
                continue
            checked += 1
            assert client.request(method, re.sub(r"\{[^}]+\}", "1", path)).status_code == 401, (method, path)
    assert checked > 30


def test_a_newcomer_cannot_reach_what_only_the_admin_or_a_creator_may(client):
    sign_up(client)
    assert client.get("/api/settings").status_code == 403
    assert client.put("/api/settings", json={"values": {}}).status_code == 403
    assert client.post("/api/settings/test-key", json={"key": "GEMINI_API_KEY", "value": ""}).status_code == 403
    assert client.get("/api/expressions").status_code == 403
    assert client.get("/api/topics/all").status_code == 403
    assert client.get("/api/topics").status_code == 403
    assert client.post("/api/topics/refresh").status_code == 403
    assert client.get("/api/assessor/token").status_code == 403
    assert client.post("/api/speech", json={"text": "hi"}).status_code == 403


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_failures_stop_counting_after_the_window():
    clock = Clock()
    failed = FailedLogins(limit=2, window_s=900, clock=clock)
    failed.failed("a@example.com")
    failed.failed("a@example.com")
    assert failed.blocked("a@example.com") and not failed.blocked("b@example.com")
    clock.now = 901
    assert not failed.blocked("a@example.com")


def test_clearing_forgets_the_failures():
    failed = FailedLogins(limit=1)
    failed.failed("a@example.com")
    failed.cleared("a@example.com")
    assert not failed.blocked("a@example.com")


def test_signups_open_again_after_the_window():
    clock = Clock()
    signups = SignupLimit(limit=2, window_s=3600, clock=clock)
    assert signups.allow() and signups.allow() and not signups.allow()
    clock.now = 3601
    assert signups.allow()
