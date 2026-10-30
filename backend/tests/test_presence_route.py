import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import presence
from app.api.deps import LOGIN_COOKIE
from app.db import Database
from app.live import presence as live_presence
from app.main import create_app
from app.wiring import Services
from tests.conftest import add_user, sample_draft, sign_in
from tests.test_api import FakeGenerator, InlineExecutor

HOME = {"origin": "http://testserver"}


def world(tmp_path):
    db = Database(tmp_path / "s.db")
    client = TestClient(create_app(db, Services(FakeGenerator()), InlineExecutor()))
    maker = add_user(db, "maker@example.com")
    return db, client, maker, db.sessions.create(sample_draft(), [], created_by=maker.id)


def url_of(session) -> str:
    return f"/api/sessions/{session.id}/presence"


def closed_with(socket) -> int:
    with pytest.raises(WebSocketDisconnect) as e:
        socket.receive_json()
    return e.value.code


def with_a_friend(tmp_path):
    db, client, maker, session = world(tmp_path)
    friend = add_user(db, "friend@example.com")
    db.shares.share(session.id, friend.id)
    other = TestClient(client.app)
    sign_in(client, db, maker)
    sign_in(other, db, friend)
    return db, client, other, friend, session


def test_no_login_is_closed_with_4401_and_hears_nothing(tmp_path):
    _, client, _, session = world(tmp_path)
    with client.websocket_connect(url_of(session), headers=HOME) as ws:
        assert closed_with(ws) == 4401


def test_no_access_and_no_session_look_the_same(tmp_path):
    db, client, _, session = world(tmp_path)
    sign_in(client, db, add_user(db, "stranger@example.com"))
    for url in (url_of(session), "/api/sessions/999/presence"):
        with client.websocket_connect(url, headers=HOME) as ws:
            assert closed_with(ws) == 4404


def test_another_origin_is_refused_before_anything_else(tmp_path):
    db, client, maker, session = world(tmp_path)
    sign_in(client, db, maker)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(url_of(session), headers={"origin": "https://evil.example"}):
            pass
    assert e.value.code == 4403


def test_no_origin_only_needs_the_login(tmp_path):
    db, client, maker, session = world(tmp_path)
    sign_in(client, db, maker)
    with client.websocket_connect(url_of(session)) as ws:
        assert ws.receive_json()["type"] == "welcome"


def test_welcome_gives_the_makers_color_and_names_no_account(tmp_path):
    db, client, maker, session = world(tmp_path)
    sign_in(client, db, maker)
    with client.websocket_connect(url_of(session), headers=HOME) as ws:
        welcome = ws.receive_json()
    assert welcome["type"] == "welcome" and welcome["you"]["color"] == 0
    assert "maker@example.com" not in json.dumps(welcome) and "user_id" not in json.dumps(welcome)


def test_two_people_hear_each_other_and_a_departure(tmp_path):
    _, mine, theirs, _, session = with_a_friend(tmp_path)
    with mine.websocket_connect(url_of(session), headers=HOME) as me:
        me.receive_json()
        with theirs.websocket_connect(url_of(session), headers=HOME) as them:
            welcome = them.receive_json()
            assert welcome["you"]["color"] == 1 and welcome["people"][0]["color"] == 0
            assert me.receive_json() == {"type": "joined", "id": welcome["you"]["id"], "color": 1, "tab": None}

            them.send_json({"type": "cursor", "tab": 0, "anchor": "brief", "x": 0.5, "y": 0.25})
            assert me.receive_json() == {"type": "cursor", "id": welcome["you"]["id"], "tab": 0, "anchor": "brief", "x": 0.5, "y": 0.25}

            me.send_json({"type": "view", "key": "chip:word:2", "value": True, "seq": 1})
            assert me.receive_json()["type"] == "view"
            assert them.receive_json()["key"] == "chip:word:2"
        assert me.receive_json() == {"type": "left", "id": welcome["you"]["id"]}


def test_ending_the_share_closes_the_socket_with_4404(tmp_path):
    db, _, theirs, friend, session = with_a_friend(tmp_path)
    with theirs.websocket_connect(url_of(session), headers=HOME) as ws:
        ws.receive_json()
        db.shares.unshare(session.id, friend.id)
        assert closed_with(ws) == 4404


def test_deleting_the_session_closes_the_socket_with_4404(tmp_path):
    db, mine, _, _, session = with_a_friend(tmp_path)
    with mine.websocket_connect(url_of(session), headers=HOME) as ws:
        ws.receive_json()
        db.sessions.delete(session.id)
        assert closed_with(ws) == 4404


def test_a_login_gone_stale_closes_at_the_next_check(tmp_path, monkeypatch):
    monkeypatch.setattr(presence, "RECHECK_S", 0.05)
    db, client, maker, session = world(tmp_path)
    token = db.accounts.start_login(maker.id)
    client.cookies.set(LOGIN_COOKIE, token)
    with client.websocket_connect(url_of(session), headers=HOME) as ws:
        ws.receive_json()
        db.accounts.end_login(token)
        assert closed_with(ws) == 4404


def test_someone_too_slow_to_keep_up_is_closed_to_start_over(tmp_path, monkeypatch):
    monkeypatch.setattr(live_presence, "MAX_QUEUED", 0)
    _, mine, theirs, _, session = with_a_friend(tmp_path)
    with mine.websocket_connect(url_of(session), headers=HOME) as me:
        me.receive_json()
        with theirs.websocket_connect(url_of(session), headers=HOME) as them:
            them.receive_json()
            assert closed_with(me) == 1013


def test_a_binary_frame_is_ignored(tmp_path):
    db, client, maker, session = world(tmp_path)
    sign_in(client, db, maker)
    with client.websocket_connect(url_of(session), headers=HOME) as ws:
        ws.receive_json()
        ws.send_bytes(b"\x00\x01")
        ws.send_json({"type": "view", "key": "k", "value": True, "seq": 1})
        assert ws.receive_json()["key"] == "k"
