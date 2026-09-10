import pytest
from fastapi.testclient import TestClient

from app.generator import GenerationError
from app.main import create_app
from app.progress import Progress, Stage
from app.store import SessionStore
from app.topics import TOPICS
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
    assert create(client)["topic"] in TOPICS


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


def test_topics_endpoint(client):
    assert client.get("/api/topics").json() == list(TOPICS)


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
