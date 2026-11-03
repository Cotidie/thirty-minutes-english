import pytest

from app.accounts import usernames
from app.db import Database
from app.main import create_app
from app.wiring import Services
from tests.conftest import add_user, client_of
from tests.test_api import FakeGenerator, InlineExecutor


@pytest.fixture
def world(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    me = add_user(db, "me@example.com", username="mina")
    for email, name in (("jo@example.com", "minjo"), ("su@example.com", "수민"), ("kim@example.com", "kim")):
        add_user(db, email, username=name)
    return db, app, me, client_of(app, db, me)


def test_a_search_gives_names_and_ids_only_never_an_email(world):
    db, _, _, client = world
    res = client.get("/api/users", params={"q": "min"})
    assert res.status_code == 200
    assert res.json() == [{"id": db.accounts.by_email("jo@example.com").id, "username": "minjo"}]


def test_a_search_finds_korean_and_leaves_out_who_searches(world):
    _, _, _, client = world
    assert [p["username"] for p in client.get("/api/users", params={"q": "민"}).json()] == ["수민"]
    assert client.get("/api/users", params={"q": "mina"}).json() == []


def test_a_search_needs_a_login(world):
    db, app, _, _ = world
    assert client_of(app, db).get("/api/users", params={"q": "min"}).status_code == 401


def test_a_new_name_comes_back_on_me(world):
    _, _, _, client = world
    res = client.put("/api/me/username", json={"username": " Mina_2 "})
    assert res.status_code == 200 and res.json()["username"] == "Mina_2"
    assert client.get("/api/auth/me").json()["username"] == "Mina_2"


def test_a_name_someone_else_has_is_a_409_and_a_bad_one_a_400(world):
    _, _, _, client = world
    res = client.put("/api/me/username", json={"username": "KIM"})
    assert res.status_code == 409 and res.json()["detail"] == "Someone already goes by that name."
    res = client.put("/api/me/username", json={"username": "a b"})
    assert res.status_code == 400 and res.json()["detail"] == usernames.RULE
    assert client.get("/api/auth/me").json()["username"] == "mina"
