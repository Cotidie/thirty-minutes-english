import pytest
from fastapi.testclient import TestClient

from app.generator import GenerationError
from app.main import create_app
from app.progress import Progress, Stage
from app.store import SessionStore
from app.topics import TOPICS

TOPIC_TEXTS = {t.text for t in TOPICS}
from tests.conftest import sample_content


class InlineExecutor:
    """Runs jobs on the calling thread so tests see a finished job right after POST."""

    def submit(self, fn, /, *args):
        fn(*args)


class FakeGenerator:
    def __init__(self):
        self.topics: list[str] = []
        self.excluded: list = []

    def generate(self, topic: str, on_progress=None, exclude=None):
        self.topics.append(topic)
        self.excluded.append(exclude)
        if on_progress:
            on_progress(Progress(Stage.SEARCHING, 2))
        return sample_content(topic=topic, title=f"About {topic}")


class FailingGenerator:
    def generate(self, topic: str, on_progress=None, exclude=None):
        raise GenerationError("claude exited 1")


@pytest.fixture
def client(tmp_path):
    gen = FakeGenerator()
    app = create_app(SessionStore(tmp_path / "s.db"), gen, InlineExecutor())
    with TestClient(app) as c:
        c.generator = gen
        yield c


def create(client, topic=None) -> dict:
    res = client.post("/api/sessions", json={"topic": topic})
    assert res.status_code == 202
    return res.json()


def test_create_session_uses_given_topic_and_finishes_job(client):
    job = create(client, "Queueing theory")
    assert job["topic"] == "Queueing theory"
    assert job["status"] == "done"
    assert job["stage"] == "searching" and job["searches"] == 2
    assert job["expected_seconds"] > 0
    session = client.get(f"/api/sessions/{job['session_id']}").json()
    assert session["content"]["article"]["title"] == "About Queueing theory"
    assert client.generator.topics == ["Queueing theory"]


def test_job_endpoint_returns_same_job(client):
    job = create(client, "X")
    fetched = client.get(f"/api/jobs/{job['id']}").json()
    assert fetched["id"] == job["id"] and fetched["session_id"] == job["session_id"]
    assert client.get("/api/jobs/nope").status_code == 404


def test_create_session_picks_topic_when_missing(client):
    assert create(client)["topic"] in TOPIC_TEXTS


def test_create_session_avoids_recent_auto_topics(client):
    seen = {create(client)["topic"] for _ in range(5)}
    assert len(seen) == 5


def test_list_and_get(client):
    sid = create(client, "X")["session_id"]
    listed = client.get("/api/sessions").json()
    assert [s["id"] for s in listed] == [sid]
    assert listed[0]["title"] == "About X"
    assert client.get(f"/api/sessions/{sid}").json()["content"]["topic"] == "X"


def test_get_missing_404(client):
    assert client.get("/api/sessions/42").status_code == 404


def test_delete_session(client):
    sid = create(client, "X")["session_id"]
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 404


def test_topics_endpoint_offers_a_stable_daily_slice(client):
    body = client.get("/api/topics").json()
    assert len(body["topics"]) == 12
    assert {t["text"] for t in body["topics"]} <= TOPIC_TEXTS
    assert body["pending"] is False  # no news source configured in tests
    assert client.get("/api/topics").json()["topics"] == body["topics"]


def test_job_reports_failure_when_generator_fails(tmp_path):
    app = create_app(SessionStore(tmp_path / "s.db"), FailingGenerator(), InlineExecutor())
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
    assert job["status"] == "failed"
    assert "claude exited 1" in job["error"]
    assert job["session_id"] is None


def test_second_generation_receives_items_from_the_first(client):
    create(client, "A")
    create(client, "B")
    first, second = client.generator.excluded
    assert not first
    assert set(second.expressions) <= {f"phrase {i}" for i in range(6)}
    assert set(second.words) <= {f"word{i}" for i in range(12)}


def test_ask_is_saved_and_listed(client):
    session_id = client.post("/api/sessions", json={"topic": "Digital twins"}).json()["session_id"]

    created = client.post(
        "/api/asks",
        json={"session_id": session_id, "user_text": "눈치 좀 챙겨", "coach_text": "Read the room.", "seconds": 11},
    )
    assert created.status_code == 201
    assert created.json()["card"] is None

    assert [a["user_text"] for a in client.get("/api/asks").json()] == ["눈치 좀 챙겨"]
    assert client.get("/api/asks", params={"session_id": session_id}).json()[0]["id"] == created.json()["id"]
    assert client.get("/api/asks", params={"session_id": session_id + 1}).json() == []


def test_ask_without_a_session_is_allowed(client):
    res = client.post("/api/asks", json={"user_text": "q", "coach_text": "a"})
    assert res.status_code == 201
    assert res.json()["session_id"] is None
    assert res.json()["seconds"] == 0


def test_ask_for_a_missing_session_is_404(client):
    res = client.post("/api/asks", json={"session_id": 999, "user_text": "q", "coach_text": "a"})
    assert res.status_code == 404


def test_ask_rejects_empty_transcripts(client):
    assert client.post("/api/asks", json={"user_text": " ", "coach_text": "a"}).status_code == 422


def test_stars_endpoint_round_trips_and_404s_on_unknown_session(client):
    sid = create(client, "X")["session_id"]
    assert client.get(f"/api/sessions/{sid}/stars").json() == {"expressions": [], "words": []}

    body = {"expressions": ["a moving target"], "words": ["mitigate"]}
    assert client.put(f"/api/sessions/{sid}/stars", json=body).json() == body
    assert client.get(f"/api/sessions/{sid}/stars").json() == body

    assert client.get("/api/sessions/999/stars").status_code == 404
    assert client.put("/api/sessions/999/stars", json=body).status_code == 404


def test_examples_stack_under_a_session_in_the_order_made(client):
    sid = create(client, "X")["session_id"]
    assert client.get("/api/examples", params={"session_id": sid}).json() == []

    body = {"session_id": sid, "expression": "phrase 0", "user_text": "I said it.", "coach_text": "I said it. Natural.", "seconds": 9}
    first = client.post("/api/examples", json=body)
    assert first.status_code == 201
    assert first.json()["expression"] == "phrase 0"
    client.post("/api/examples", json={**body, "user_text": "Again."})

    listed = client.get("/api/examples", params={"session_id": sid}).json()
    assert [e["user_text"] for e in listed] == ["I said it.", "Again."]
    assert client.get("/api/examples", params={"session_id": sid + 1}).json() == []

    assert client.post("/api/examples", json={**body, "session_id": 999}).status_code == 404
    assert client.post("/api/examples", json={**body, "coach_text": " "}).status_code == 422

    client.delete(f"/api/sessions/{sid}")
    assert client.get("/api/examples", params={"session_id": sid}).json() == []


class HeldExecutor:
    """Keeps submitted jobs unstarted until the test releases them."""

    def __init__(self):
        self.held: list = []

    def submit(self, fn, /, *args):
        self.held.append((fn, args))

    def release(self):
        for fn, args in self.held:
            fn(*args)
        self.held.clear()


def test_jobs_endpoint_lists_only_running_jobs(tmp_path):
    executor = HeldExecutor()
    app = create_app(SessionStore(tmp_path / "s.db"), FakeGenerator(), executor)
    with TestClient(app) as client:
        assert client.get("/api/jobs").json() == []
        first = create(client, "First")
        second = create(client, "Second")
        assert [j["id"] for j in client.get("/api/jobs").json()] == [first["id"], second["id"]]
        assert client.get("/api/jobs").json()[0]["status"] == "running"

        executor.release()
        assert client.get("/api/jobs").json() == []
