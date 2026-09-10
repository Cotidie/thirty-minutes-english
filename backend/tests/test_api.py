import pytest
from fastapi.testclient import TestClient

from app.generator import GenerationError
from app.main import create_app
from app.store import SessionStore
from app.topics import TOPICS
from tests.conftest import sample_content


class FakeGenerator:
    def __init__(self):
        self.topics: list[str] = []

    def generate(self, topic: str):
        self.topics.append(topic)
        return sample_content(topic=topic, title=f"About {topic}")


class FailingGenerator:
    def generate(self, topic: str):
        raise GenerationError("claude exited 1")


@pytest.fixture
def client(tmp_path):
    gen = FakeGenerator()
    app = create_app(SessionStore(tmp_path / "s.db"), gen)
    with TestClient(app) as c:
        c.generator = gen
        yield c


def test_create_session_uses_given_topic(client):
    res = client.post("/api/sessions", json={"topic": "Queueing theory"})
    assert res.status_code == 201
    body = res.json()
    assert body["topic"] == "Queueing theory"
    assert body["content"]["article"]["title"] == "About Queueing theory"
    assert client.generator.topics == ["Queueing theory"]


def test_create_session_picks_topic_when_missing(client):
    res = client.post("/api/sessions", json={})
    assert res.status_code == 201
    assert res.json()["topic"] in TOPICS


def test_create_session_avoids_recent_auto_topics(client):
    seen = {client.post("/api/sessions", json={}).json()["topic"] for _ in range(5)}
    assert len(seen) == 5


def test_list_and_get(client):
    sid = client.post("/api/sessions", json={"topic": "X"}).json()["id"]
    listed = client.get("/api/sessions").json()
    assert [s["id"] for s in listed] == [sid]
    assert listed[0]["title"] == "About X"
    assert client.get(f"/api/sessions/{sid}").json()["content"]["topic"] == "X"


def test_get_missing_404(client):
    assert client.get("/api/sessions/42").status_code == 404


def test_delete_session(client):
    sid = client.post("/api/sessions", json={"topic": "X"}).json()["id"]
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 404


def test_topics_endpoint(client):
    assert client.get("/api/topics").json() == list(TOPICS)


def test_create_returns_502_when_generator_fails(tmp_path):
    app = create_app(SessionStore(tmp_path / "s.db"), FailingGenerator())
    with TestClient(app) as c:
        res = c.post("/api/sessions", json={"topic": "X"})
    assert res.status_code == 502
    assert "claude exited 1" in res.json()["detail"]
