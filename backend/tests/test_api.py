import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.generation.generator import VOCABULARY_COUNT
from app.generation.jobs import DEFAULT_STAGE_SECONDS, EXPRESSION_COUNT
from app.generation.progress import Progress, Stage
from app.llm import GenerationError
from app.main import create_app
from app.topics.pool import TOPICS
from app.wiring import Services
from app.pictures.files import PictureFiles
from app.pictures.scenes import Scene

TOPIC_TEXTS = {t.text for t in TOPICS}
from tests.conftest import sample_draft, seed_expressions


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
        return sample_draft(topic=topic, title=f"About {topic}")


class FailingGenerator:
    def generate(self, topic: str, on_progress=None, exclude=None):
        raise GenerationError("claude exited 1")


@pytest.fixture
def client(tmp_path):
    gen = FakeGenerator()
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    app = create_app(db, Services(gen), InlineExecutor())
    with TestClient(app) as c:
        c.generator = gen
        yield c


def content_of(client, session_id: int) -> dict:
    return client.get(f"/api/sessions/{session_id}").json()["content"]


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
    content = content_of(client, sid)
    assert content["topic"] == "X"
    assert [p["text"] for p in content["article"]["paragraphs"]] == ["One.", "Two two.", "Three."]
    assert "body" not in content["article"] and all(isinstance(p["id"], int) for p in content["article"]["paragraphs"])
    assert len(content["expressions"]) == EXPRESSION_COUNT and all(isinstance(e["id"], int) for e in content["expressions"])
    assert all(isinstance(v["id"], int) for v in content["vocabulary"])


def test_a_session_with_an_empty_corpus_has_no_expressions(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), InlineExecutor())
    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={"topic": "X"}).json()["session_id"]
        assert content_of(c, sid)["expressions"] == []


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
    app = create_app(Database(tmp_path / "s.db"), Services(FailingGenerator()), InlineExecutor())
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
    assert job["status"] == "failed"
    assert "claude exited 1" in job["error"]
    assert job["session_id"] is None


def test_a_failed_job_says_why_in_the_log(tmp_path, caplog):
    app = create_app(Database(tmp_path / "s.db"), Services(FailingGenerator()), InlineExecutor())
    with TestClient(app) as c, caplog.at_level("WARNING", logger="app.generation.jobs"):
        job = c.post("/api/sessions", json={"topic": "X"}).json()
    assert f"job {job['id']}: failed after" in caplog.text
    assert "claude exited 1" in caplog.text


def test_a_failed_job_stays_listed_until_it_is_dismissed(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FailingGenerator()), InlineExecutor())
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
        listed = c.get("/api/jobs").json()
        assert [(j["id"], j["status"]) for j in listed] == [(job["id"], "failed")]
        assert "claude exited 1" in listed[0]["error"]
        assert c.get("/api/jobs").json()[0]["elapsed_seconds"] == listed[0]["elapsed_seconds"]  # the clock stopped

        assert c.delete(f"/api/jobs/{job['id']}").json()["status"] == "failed"
        assert c.get("/api/jobs").json() == []
        assert c.get(f"/api/jobs/{job['id']}").status_code == 404


class FakeIllustrator:
    """Draws nothing real: each picture is a row in the picture table and a file, as the real one leaves them."""

    def __init__(self, db: Database, error: Exception | None = None, seconds: float | None = None):
        self.files = PictureFiles(db.images_dir)
        self.pictures = db.pictures
        self.error = error
        self.seconds = seconds
        self.job_ids: list[str] = []
        self.styles: list[str] = []

    def expected_seconds(self, count: int) -> float | None:
        return None if self.seconds is None else self.seconds * count

    def count(self, words) -> int:
        return 2 * len(words)

    def draw(self) -> int:
        picture_id = self.pictures.add("fake", 1.0, None)
        self.files.write(picture_id, b"PNG")
        return picture_id

    def illustrate(self, job_id: str, words, on_drawn=None, on_picture=None):
        self.job_ids.append(job_id)
        if on_drawn:
            on_drawn(self.count(words))
        if self.error:
            raise self.error
        for i in range(len(words)):
            on_picture(i, "image", self.draw())
            on_picture(i, "example_image", self.draw())

    def redraw(self, scene, style=""):
        self.styles.append(style)
        return self.draw()

    def redraw_example(self, item, style=""):
        self.styles.append(style)
        return self.draw()


def with_pictures(tmp_path, illustrator_of=FakeIllustrator, **services):
    db = Database(tmp_path / "s.db")
    illustrator = illustrator_of(db)
    app = create_app(db, Services(FakeGenerator(), illustrator=illustrator, **services), InlineExecutor())
    return app, illustrator, db


def test_pictures_are_drawn_after_the_text_and_saved_with_the_session(tmp_path):
    app, illustrator, db = with_pictures(tmp_path)
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
        words = content_of(c, job["session_id"])["vocabulary"]
    assert illustrator.job_ids == [job["id"]]
    assert job["stage"] == "illustrating"
    assert job["pictures_done"] == 20  # the fake reports both pictures of every word drawn
    assert (words[0]["image"], words[0]["example_image"], words[9]["example_image"]) == ("1.png", "2.png", "20.png")
    assert db.pictures.stats()["fake"].seconds == 1.0


def test_the_session_can_be_opened_while_its_pictures_are_drawn(tmp_path):
    seen: dict = {}

    class Watched(FakeIllustrator):
        def illustrate(self, job_id, words, on_drawn=None, on_picture=None):
            on_picture(0, "example_image", self.draw())
            job = c.get(f"/api/jobs/{job_id}").json()
            seen.update(job=job, session=c.get(f"/api/sessions/{job['session_id']}").json())

    app, _, _ = with_pictures(tmp_path, Watched)
    with TestClient(app) as c:
        c.post("/api/sessions", json={"topic": "X"})
    assert (seen["job"]["status"], seen["job"]["stage"]) == ("running", "illustrating")
    words = seen["session"]["content"]["vocabulary"]
    assert (words[0]["example_image"], words[0]["image"], words[1]["example_image"]) == ("1.png", None, None)


def test_a_session_still_goes_out_when_the_pictures_fail(tmp_path):
    app, _, _ = with_pictures(tmp_path, lambda db: FakeIllustrator(db, GenerationError("openrouter down")))
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
        words = content_of(c, job["session_id"])["vocabulary"]
    assert job["status"] == "done"
    assert words[0]["image"] is None


def test_deleting_a_session_removes_its_picture_files(tmp_path):
    app, _, db = with_pictures(tmp_path)
    with TestClient(app) as c:
        kept = c.post("/api/sessions", json={"topic": "Kept"}).json()["session_id"]
        gone = c.post("/api/sessions", json={"topic": "Gone"}).json()["session_id"]
        assert len(list(db.images_dir.iterdir())) == 40
        assert c.delete(f"/api/sessions/{gone}").status_code == 204
    assert sorted(f.name for f in db.images_dir.iterdir()) == sorted(f"{i}.png" for i in range(1, 21))
    assert kept != gone


class FakeSceneWriter:
    def write(self, item):
        return Scene(f"another scene for {item.word}", f"why it is {item.word}")


def test_a_word_can_be_redrawn_in_a_chosen_style_and_the_session_keeps_it(tmp_path):
    app, illustrator, db = with_pictures(tmp_path, scene_writer=FakeSceneWriter())
    files = PictureFiles(db.images_dir)
    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={"topic": "X"}).json()["session_id"]  # word 1 shows pictures 3 and 4
        res = c.post(f"/api/sessions/{sid}/pictures/1", json={"style": "comic"})
        assert res.status_code == 200
        assert (res.json()["scene"], res.json()["caption"], res.json()["image"]) == ("another scene for word1", "why it is word1", "21.png")
        assert content_of(c, sid)["vocabulary"][1]["image"] == "21.png"
        example = c.post(f"/api/sessions/{sid}/pictures/1", json={"face": "example"}).json()
        assert (example["example_image"], example["image"]) == ("22.png", "21.png")
        assert c.post(f"/api/sessions/{sid}/pictures/99", json={}).status_code == 404
    assert illustrator.styles == ["comic", ""]
    assert not files.path(3).exists() and not files.path(4).exists()  # only the picture each redraw replaced
    assert files.path(5).exists() and files.path(21).exists() and files.path(22).exists()


def test_redraw_after_the_session_went_away_leaves_no_file(tmp_path):
    class Vanishing(FakeIllustrator):
        def redraw(self, scene, style=""):
            picture = super().redraw(scene, style)
            assert c.delete(f"/api/sessions/{sid}").status_code == 204
            return picture

    app, _, db = with_pictures(tmp_path, Vanishing, scene_writer=FakeSceneWriter())
    with TestClient(app) as c:
        sid = c.post("/api/sessions", json={"topic": "X"}).json()["session_id"]
        assert c.post(f"/api/sessions/{sid}/pictures/1", json={}).status_code == 404
    assert list(db.images_dir.iterdir()) == []


def test_redraw_is_503_while_pictures_are_off(client):
    sid = create(client, "X")["session_id"]
    assert client.post(f"/api/sessions/{sid}/pictures/0", json={}).status_code == 503


def test_second_generation_receives_the_words_of_the_first(client):
    create(client, "A")
    create(client, "B")
    first, second = client.generator.excluded
    assert not first
    assert set(second.words) <= {f"word{i}" for i in range(VOCABULARY_COUNT)}


def test_stars_endpoint_round_trips_and_404s_on_unknown_session(client):
    sid = create(client, "X")["session_id"]
    assert client.get(f"/api/sessions/{sid}/stars").json() == {"expressions": [], "words": []}

    content = content_of(client, sid)
    body = {"expressions": [content["expressions"][1]["id"]], "words": [content["vocabulary"][3]["id"]]}
    assert client.put(f"/api/sessions/{sid}/stars", json=body).json() == body
    assert client.get(f"/api/sessions/{sid}/stars").json() == body

    assert client.get("/api/sessions/999/stars").status_code == 404
    assert client.put("/api/sessions/999/stars", json=body).status_code == 404


def test_note_endpoint_round_trips_and_404s_on_unknown_session(client):
    sid = create(client, "X")["session_id"]
    assert client.get(f"/api/sessions/{sid}/note").json() == {"text": ""}

    body = {"text": "hedge 발음 다시\nask about 'moving target'"}
    assert client.put(f"/api/sessions/{sid}/note", json=body).json() == body
    assert client.get(f"/api/sessions/{sid}/note").json() == body

    assert client.get("/api/sessions/999/note").status_code == 404
    assert client.put("/api/sessions/999/note", json=body).status_code == 404


def test_examples_stack_under_a_session_in_the_order_made(client):
    sid = create(client, "X")["session_id"]
    assert client.get("/api/examples", params={"session_id": sid}).json() == []
    content = content_of(client, sid)
    expression, word = content["expressions"][0]["id"], content["vocabulary"][2]["id"]

    body = {"session_id": sid, "expression_id": expression, "user_text": "I said it.", "coach_text": "I said it. Natural.", "seconds": 9}
    first = client.post("/api/examples", json=body)
    assert first.status_code == 201
    assert (first.json()["expression_id"], first.json()["vocabulary_id"]) == (expression, None)
    client.post("/api/examples", json={"session_id": sid, "vocabulary_id": word, "user_text": "Again.", "coach_text": "Good."})

    listed = client.get("/api/examples", params={"session_id": sid}).json()
    assert [(e["user_text"], e["expression_id"], e["vocabulary_id"]) for e in listed] == [("I said it.", expression, None), ("Again.", None, word)]
    assert client.get("/api/examples", params={"session_id": sid + 1}).json() == []

    assert client.post("/api/examples", json={**body, "session_id": 999}).status_code == 404
    assert client.post("/api/examples", json={**body, "coach_text": " "}).status_code == 422
    assert client.post("/api/examples", json={**body, "vocabulary_id": word}).status_code == 422  # one or the other
    assert client.post("/api/examples", json={k: v for k, v in body.items() if k != "expression_id"}).status_code == 422

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


def test_jobs_endpoint_drops_finished_jobs(tmp_path):
    executor = HeldExecutor()
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), executor)
    with TestClient(app) as client:
        assert client.get("/api/jobs").json() == []
        first = create(client, "First")
        second = create(client, "Second")
        assert [j["id"] for j in client.get("/api/jobs").json()] == [first["id"], second["id"]]
        assert client.get("/api/jobs").json()[0]["status"] == "running"

        executor.release()
        assert client.get("/api/jobs").json() == []


def test_an_example_for_an_expression_not_in_the_session_is_404(client):
    first = create(client, "A")["session_id"]
    second = create(client, "B")["session_id"]
    taught_elsewhere = {e["id"] for e in content_of(client, first)["expressions"]} - {e["id"] for e in content_of(client, second)["expressions"]}
    other_word = content_of(client, first)["vocabulary"][0]["id"]
    body = {"session_id": second, "user_text": "x", "coach_text": "y"}
    for target in [{"expression_id": 999}, {"vocabulary_id": other_word}, *({"expression_id": e} for e in taught_elsewhere)]:
        res = client.post("/api/examples", json={**body, **target})
        assert (res.status_code, res.json()["detail"]) == (404, "not taught in this session")
    assert client.get("/api/examples", params={"session_id": second}).json() == []


def first_paragraph(client, session_id: int) -> int:
    return content_of(client, session_id)["article"]["paragraphs"][0]["id"]


def test_readings_keep_their_marks_and_list_per_session(client):
    session_id = client.post("/api/sessions", json={"topic": "Digital twins"}).json()["session_id"]
    sounds = [{"phoneme": "v", "score": 8, "weak": True, "heard": "b"}, {"phoneme": "ɛ", "score": 90, "weak": False}]
    body = {
        "paragraph_id": first_paragraph(client, session_id),
        "user_text": "researchers berified it",
        "seconds": 31,
        "corrections": [
            {"word": "verified", "heard": "b for v", "fix": "vɛrɪfaɪd", "repeated_ok": True, "at": 1, "score": 41, "sounds": sounds}
        ],
    }
    created = client.post("/api/readings", json=body)
    assert created.status_code == 201
    assert created.json()["corrections"][0]["word"] == "verified"
    assert created.json()["paragraph_id"] == body["paragraph_id"]
    assert client.post("/api/readings", json={**body, "paragraph_id": 999}).status_code == 404

    listed = client.get("/api/readings", params={"session_id": session_id}).json()
    assert [r["id"] for r in listed] == [created.json()["id"]]
    [mark] = listed[0]["corrections"]
    assert (mark["repeated_ok"], mark["at"], mark["score"]) == (True, 1, 41)
    assert [(s["phoneme"], s["heard"]) for s in mark["sounds"]] == [("v", "b"), ("ɛ", None)]
    assert client.get("/api/readings", params={"session_id": session_id + 1}).json() == []


def test_a_reading_kept_before_marks_were_saved_has_no_place_on_the_paragraph(client):
    session_id = client.post("/api/sessions", json={"topic": "Digital twins"}).json()["session_id"]
    old = {"word": "verified", "heard": "b for v", "fix": "vɛrɪfaɪd"}
    client.post("/api/readings", json={"paragraph_id": first_paragraph(client, session_id), "user_text": "p", "seconds": 3, "corrections": [old]})
    [mark] = client.get("/api/readings", params={"session_id": session_id}).json()[0]["corrections"]
    assert (mark["at"], mark["sounds"]) == (-1, [])


def test_a_reading_without_corrections_is_a_clean_read(client):
    session_id = client.post("/api/sessions", json={"topic": "Digital twins"}).json()["session_id"]
    body = {"paragraph_id": first_paragraph(client, session_id), "user_text": "researchers verified it"}
    assert client.post("/api/readings", json=body).json()["corrections"] == []


class DeferredExecutor:
    """Holds the job until the test runs it, so the test can act on a running job."""

    def __init__(self):
        self.pending: list = []

    def submit(self, fn, /, *args):
        self.pending.append((fn, args))

    def run(self):
        for fn, args in self.pending:
            fn(*args)


def test_a_cancelled_job_stops_and_saves_nothing(tmp_path):
    executor = DeferredExecutor()
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), executor)
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
        cancelled = c.delete(f"/api/jobs/{job['id']}").json()
        executor.run()
        after = c.get(f"/api/jobs/{job['id']}").json()
        assert c.get("/api/sessions").json() == []
        assert c.get("/api/jobs").json() == []
        assert c.delete("/api/jobs/nope").status_code == 404
    assert cancelled["status"] == after["status"] == "cancelled"
    assert after["session_id"] is None


def test_a_fresh_job_expects_the_default_time_of_every_stage(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), DeferredExecutor())
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
    assert job["expected_seconds"] == sum(DEFAULT_STAGE_SECONDS.values())
    assert job["stage_expected_seconds"] == DEFAULT_STAGE_SECONDS[Stage.STARTING]


def test_a_job_foresees_its_pictures_from_the_picture_model_time_here(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator(), illustrator=FakeIllustrator(db, seconds=7)), DeferredExecutor())
    with TestClient(app) as c:
        job = c.post("/api/sessions", json={"topic": "X"}).json()
    others = sum(s for stage, s in DEFAULT_STAGE_SECONDS.items() if stage != Stage.ILLUSTRATING)
    assert job["expected_seconds"] == others + 7 * 20  # two pictures a word


def test_stage_estimates_survive_a_restart(tmp_path):
    path = tmp_path / "s.db"
    with TestClient(create_app(Database(path), Services(FakeGenerator()), InlineExecutor())) as c:
        c.post("/api/sessions", json={"topic": "X"})
    with TestClient(create_app(Database(path), Services(FakeGenerator()), DeferredExecutor())) as c:
        job = c.post("/api/sessions", json={"topic": "Y"}).json()
    assert job["stage_expected_seconds"] < DEFAULT_STAGE_SECONDS[Stage.STARTING]  # the first run's time, not the default
