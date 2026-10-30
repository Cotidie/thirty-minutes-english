from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.generation.jobs import EXPRESSION_COUNT
from app.main import create_app
from app.pictures.files import PictureFiles
from app.wiring import Services
from tests.conftest import add_user, seed_expressions, sign_in
from tests.test_api import FailingGenerator, FakeGenerator, InlineExecutor


def client_of(app, db, user=None) -> TestClient:
    client = TestClient(app)
    if user is not None:
        sign_in(client, db, user)
    return client


@pytest.fixture
def world(tmp_path):
    """One session made by `creator` and shared with `sharee`; `stranger` may create but has no part in it."""
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT + 3)
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    accounts = {
        "creator": add_user(db, "creator@example.com", can_create=True),
        "sharee": add_user(db, "sharee@example.com"),
        "newcomer": add_user(db, "newcomer@example.com"),
        "stranger": add_user(db, "stranger@example.com", can_create=True),
        "admin": add_user(db, "boss@example.com", admin=True),
    }
    clients = {name: client_of(app, db, user) for name, user in accounts.items()}
    job = clients["creator"].post("/api/sessions", json={"topic": "Trams"}).json()
    db.shares.share(job["session_id"], accounts["sharee"].id)
    return SimpleNamespace(db=db, app=app, sid=job["session_id"], job_id=job["id"], anon=client_of(app, db), accounts=accounts, **clients)


@pytest.mark.parametrize(
    "method,path,anon,newcomer,sharee,creator,admin",
    [
        ("GET", "/api/sessions/{sid}", 401, 404, 200, 200, 200),
        ("GET", "/api/sessions/{sid}/stars", 401, 404, 200, 200, 200),
        ("GET", "/api/sessions/{sid}/note", 401, 404, 200, 200, 200),
        ("GET", "/api/examples?session_id={sid}", 401, 404, 200, 200, 200),
        ("GET", "/api/summaries?session_id={sid}", 401, 404, 200, 200, 200),
        ("GET", "/api/readings?session_id={sid}", 401, 404, 200, 200, 200),
        ("POST", "/api/sessions/{sid}/expressions", 401, 404, 200, 200, 200),
        ("DELETE", "/api/sessions/{sid}", 401, 404, 403, 204, 403),
        ("GET", "/api/settings", 401, 403, 403, 403, 200),
        ("GET", "/api/expressions", 401, 403, 403, 403, 200),
        ("GET", "/api/topics/all", 401, 403, 403, 403, 200),
        ("GET", "/api/topics", 401, 403, 403, 200, 200),
        ("GET", "/api/assessor/token", 401, 403, 503, 503, 503),
    ],
)
def test_who_gets_what(world, method, path, anon, newcomer, sharee, creator, admin):
    expected = {"anon": anon, "newcomer": newcomer, "sharee": sharee, "admin": admin, "creator": creator}
    target = path.format(sid=world.sid)
    for who, status in expected.items():  # the creator comes last: a delete must not spoil the others' answers
        assert getattr(world, who).request(method, target).status_code == status, who


def test_a_stranger_who_may_create_still_gets_a_404_on_someone_elses_session(world):
    assert world.stranger.get(f"/api/sessions/{world.sid}").status_code == 404
    assert world.stranger.delete(f"/api/sessions/{world.sid}").status_code == 404
    assert world.stranger.post(f"/api/sessions/{world.sid}/pictures/0", json={}).status_code == 404
    assert world.stranger.get("/api/sessions/999").status_code == 404


def test_the_list_shows_only_my_sessions_and_those_shared_with_me(world):
    [mine] = world.creator.get("/api/sessions").json()
    assert (mine["id"], mine["mine"], mine["shared_by"]) == (world.sid, True, None)
    [shared] = world.sharee.get("/api/sessions").json()
    assert (shared["id"], shared["mine"], shared["shared_by"]) == (world.sid, False, "creator@example.com")
    assert world.newcomer.get("/api/sessions").json() == []
    assert world.admin.get("/api/sessions").json() == []


def test_a_session_says_whose_it_is(world):
    assert world.creator.get(f"/api/sessions/{world.sid}").json()["mine"] is True
    shared = world.sharee.get(f"/api/sessions/{world.sid}").json()
    assert (shared["mine"], shared["shared_by"]) == (False, "creator@example.com")
    assert world.admin.get(f"/api/sessions/{world.sid}").json()["mine"] is False


def test_only_an_approved_account_can_start_a_session(world):
    assert world.newcomer.post("/api/sessions", json={"topic": "X"}).status_code == 403
    assert world.sharee.post("/api/sessions", json={"topic": "X"}).status_code == 403
    assert world.stranger.post("/api/sessions", json={"topic": "X"}).status_code == 202
    assert world.admin.post("/api/sessions", json={"topic": "X"}).status_code == 202


def test_sharee_may_change_expressions_and_keep_notes_but_not_draw_or_delete(world):
    assert world.sharee.put(f"/api/sessions/{world.sid}/note", json={"text": "hi"}).status_code == 200
    assert world.creator.get(f"/api/sessions/{world.sid}/note").json()["text"] == "hi"
    expression = world.sharee.get(f"/api/sessions/{world.sid}").json()["content"]["expressions"][0]["id"]
    assert world.sharee.post(f"/api/sessions/{world.sid}/expressions/{expression}/swap").status_code == 200
    assert world.sharee.post(f"/api/sessions/{world.sid}/pictures/0", json={}).status_code == 403


def test_an_approval_taken_away_stops_new_spending_but_keeps_my_sessions(world):
    world.db.accounts.set_can_create(world.accounts["creator"].id, False)
    assert world.creator.post("/api/sessions", json={"topic": "X"}).status_code == 403
    assert world.creator.post(f"/api/sessions/{world.sid}/pictures/0", json={}).status_code == 403
    assert world.creator.get(f"/api/sessions/{world.sid}").status_code == 200
    assert world.creator.get("/api/assessor/token").status_code == 503  # past the check: pictures are just off here
    assert world.sharee.get(f"/api/sessions/{world.sid}").status_code == 200


def test_jobs_are_seen_and_closed_only_by_who_started_them(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FailingGenerator()), InlineExecutor())
    mine = client_of(app, db, add_user(db, "me@example.com", can_create=True))
    other = client_of(app, db, add_user(db, "other@example.com", can_create=True))
    job = mine.post("/api/sessions", json={"topic": "X"}).json()
    assert [j["id"] for j in mine.get("/api/jobs").json()] == [job["id"]]
    assert other.get("/api/jobs").json() == []
    assert other.get(f"/api/jobs/{job['id']}").status_code == 404
    assert other.delete(f"/api/jobs/{job['id']}").status_code == 404
    assert mine.get(f"/api/jobs/{job['id']}").status_code == 200
    assert mine.delete(f"/api/jobs/{job['id']}").status_code == 200


def test_an_image_is_served_only_to_who_can_open_its_session(world):
    session = world.creator.get(f"/api/sessions/{world.sid}").json()
    word = session["content"]["vocabulary"][0]["id"]
    picture = world.db.pictures.add(None, None, None)
    PictureFiles(world.db.images_dir).write(picture, b"PNG")
    world.db.sessions.replace_picture(word, "image", picture)
    res = world.sharee.get(f"/api/images/{picture}.png")
    assert res.status_code == 200 and res.content == b"PNG" and res.headers["content-type"] == "image/png"
    assert res.headers["cache-control"] == "private, max-age=86400"
    assert world.creator.get(f"/api/images/{picture}.png").status_code == 200
    assert world.admin.get(f"/api/images/{picture}.png").status_code == 200
    assert world.stranger.get(f"/api/images/{picture}.png").status_code == 404
    assert world.anon.get(f"/api/images/{picture}.png").status_code == 401


@pytest.mark.parametrize("name", ["999.png", "1.jpg", "secret", "1.png.bak", "..%2Fsessions.db"])
def test_a_name_that_is_not_a_shown_picture_is_a_404(world, name):
    assert world.creator.get(f"/api/images/{name}").status_code == 404


def test_a_picture_row_whose_file_is_gone_is_a_404(world):
    word = world.creator.get(f"/api/sessions/{world.sid}").json()["content"]["vocabulary"][0]["id"]
    picture = world.db.pictures.add(None, None, None)
    world.db.sessions.replace_picture(word, "image", picture)
    assert world.creator.get(f"/api/images/{picture}.png").status_code == 404


def test_a_record_on_someone_elses_session_is_a_404(world):
    content = world.creator.get(f"/api/sessions/{world.sid}").json()["content"]
    paragraph, word = content["article"]["paragraphs"][0]["id"], content["vocabulary"][0]["id"]
    reading = {"paragraph_id": paragraph, "user_text": "u", "seconds": 1, "corrections": []}
    example = {"session_id": world.sid, "vocabulary_id": word, "user_text": "u", "coach_text": "c", "seconds": 1}
    assert world.stranger.post("/api/readings", json=reading).status_code == 404
    assert world.stranger.post("/api/examples", json=example).status_code == 404
    assert world.sharee.post("/api/readings", json=reading).status_code == 201
    assert world.sharee.post("/api/examples", json=example).status_code == 201
    assert len(world.creator.get(f"/api/readings?session_id={world.sid}").json()) == 1


def test_the_creator_shares_by_email_and_the_friend_can_open_it(world):
    assert world.newcomer.get(f"/api/sessions/{world.sid}").status_code == 404
    res = world.creator.post(f"/api/sessions/{world.sid}/shares", json={"email": " Newcomer@Example.com "})
    assert res.status_code == 201
    assert [e["email"] for e in res.json()] == ["newcomer@example.com", "sharee@example.com"]
    assert res.json()[0]["user_id"] == world.accounts["newcomer"].id
    assert world.newcomer.get(f"/api/sessions/{world.sid}").status_code == 200
    assert [e["email"] for e in world.creator.get(f"/api/sessions/{world.sid}/shares").json()] == ["newcomer@example.com", "sharee@example.com"]


def test_sharing_with_an_email_nobody_uses_is_a_404_saying_so(world):
    res = world.creator.post(f"/api/sessions/{world.sid}/shares", json={"email": "nobody@example.com"})
    assert res.status_code == 404 and res.json()["detail"] == "No account uses that email."


def test_sharing_twice_or_with_myself_changes_nothing(world):
    before = world.creator.get(f"/api/sessions/{world.sid}/shares").json()
    assert world.creator.post(f"/api/sessions/{world.sid}/shares", json={"email": "sharee@example.com"}).json() == before
    assert world.creator.post(f"/api/sessions/{world.sid}/shares", json={"email": "creator@example.com"}).json() == before


def test_only_the_creator_manages_shares(world):
    sharee_id = world.accounts["sharee"].id
    for who in (world.sharee, world.admin):
        assert who.get(f"/api/sessions/{world.sid}/shares").status_code == 403
        assert who.post(f"/api/sessions/{world.sid}/shares", json={"email": "stranger@example.com"}).status_code == 403
        assert who.delete(f"/api/sessions/{world.sid}/shares/{sharee_id}").status_code == 403
    assert world.stranger.get(f"/api/sessions/{world.sid}/shares").status_code == 404


def test_an_approval_taken_away_stops_new_shares_but_not_ending_them(world):
    world.db.accounts.set_can_create(world.accounts["creator"].id, False)
    assert world.creator.post(f"/api/sessions/{world.sid}/shares", json={"email": "stranger@example.com"}).status_code == 403
    assert world.creator.get(f"/api/sessions/{world.sid}/shares").status_code == 200
    assert world.creator.delete(f"/api/sessions/{world.sid}/shares/{world.accounts['sharee'].id}").status_code == 204
    assert world.sharee.get(f"/api/sessions/{world.sid}").status_code == 404


def test_ending_a_share_that_is_not_there_is_a_404(world):
    assert world.creator.delete(f"/api/sessions/{world.sid}/shares/{world.accounts['stranger'].id}").status_code == 404


def test_removing_a_session_from_my_list_keeps_it_for_everyone_else(world):
    assert world.sharee.delete(f"/api/sessions/{world.sid}/shares/me").status_code == 204
    assert world.sharee.get(f"/api/sessions/{world.sid}").status_code == 404
    assert world.sharee.get("/api/sessions").json() == []
    assert world.creator.get(f"/api/sessions/{world.sid}").status_code == 200


def test_shares_me_is_a_404_for_whoever_has_no_share(world):
    assert world.creator.delete(f"/api/sessions/{world.sid}/shares/me").status_code == 404
    assert world.stranger.delete(f"/api/sessions/{world.sid}/shares/me").status_code == 404
    assert world.admin.delete(f"/api/sessions/{world.sid}/shares/me").status_code == 404
