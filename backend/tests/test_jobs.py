import sqlite3
from io import BytesIO

import httpx2
import pytest
from PIL import Image as PILImage

from app.db import Database
from app.llm import GenerationError
from app.models import FigureDraft
from app.pictures.figures import SourceImages
from app.pictures.files import PictureFiles
from app.pictures.illustrator import Illustrator
from app.pictures.painters import Drawn
from app.generation.jobs import DEFAULT_STAGE_SECONDS, EXPRESSION_COUNT, Job, JobRunner
from app.generation.progress import Progress, Stage
from tests.conftest import add_user, sample_draft, seed_expressions


class InlineExecutor:
    def submit(self, fn, /, *args):
        fn(*args)


class Recording:
    """A generator that hands back the sample draft (with `figures`, when given) and keeps what it was told to avoid."""

    def __init__(self, figures: list[FigureDraft] = ()) -> None:
        self.excluded = []
        self.figures = list(figures)

    def generate(self, topic, on_progress=None, exclude=None):
        self.excluded.append(exclude)
        if on_progress:
            on_progress(Progress(Stage.SEARCHING, 1))
        draft = sample_draft(topic=topic)
        draft.article.figures = self.figures
        return draft


def photo(width: int = 800) -> bytes:
    out = BytesIO()
    PILImage.new("RGB", (width, 600), (40, 90, 160)).save(out, "JPEG")
    return out.getvalue()


async def web(url: str) -> bytes:
    """Every page's images download, except those at gone.example."""
    if "gone.example" in url:
        raise httpx2.ConnectError("gone")
    return photo()


def runner_over(db: Database) -> JobRunner:
    files = PictureFiles(db.images_dir)
    return JobRunner(db.sessions, db.expressions, db.stages, InlineExecutor(), SourceImages(db.pictures, files, web))


def test_a_finished_job_saves_the_draft_with_expressions_from_the_corpus(tmp_path):
    db = Database(tmp_path / "s.db")
    corpus = set(seed_expressions(db, EXPRESSION_COUNT + 2))
    job = runner_over(db).start("Trams", Recording())
    assert job.status == "done"
    content = db.sessions.get(job.session_id).content
    assert content.topic == "Trams" and len(content.expressions) == EXPRESSION_COUNT
    assert {e.id for e in content.expressions} <= corpus
    second = runner_over(db).start("Trams again", Recording())
    taught_twice = {e.id for e in content.expressions} & {e.id for e in db.sessions.get(second.session_id).content.expressions}
    assert len(taught_twice) == EXPRESSION_COUNT - 2  # the two never taught come first


def test_an_empty_corpus_makes_a_session_without_expressions(tmp_path):
    db = Database(tmp_path / "s.db")
    job = runner_over(db).start("Trams", Recording())
    assert db.sessions.get(job.session_id).content.expressions == []


def test_the_next_job_is_told_the_words_earlier_sessions_taught(tmp_path):
    db = Database(tmp_path / "s.db")
    generator = Recording()
    runner_over(db).start("A", generator)
    runner_over(db).start("B", generator)
    assert not generator.excluded[0]
    words = set(generator.excluded[1].words)
    assert words and words <= {v.word for v in sample_draft().vocabulary}


def test_stage_times_of_a_finished_run_are_kept_and_become_the_next_estimate(tmp_path):
    db = Database(tmp_path / "s.db")
    runner_over(db).start("A", Recording())
    assert len(db.stages.recent(Stage.SEARCHING)) == 1
    for stage in Stage:
        db.stages.add(stage, 4.0)
        db.stages.add(stage, 4.0)
    fresh = runner_over(db)  # a restart: the estimate comes from the database
    job = Job(id="j", topic="t")
    job.stage_seconds = {Stage.STARTING: 2.0}
    job.progress = Progress(Stage.SEARCHING, 1)
    # starting as it took (2), searching at least its median (4), the four after it at 4 each
    assert fresh.expected_seconds(job) == 2 + 4 + 4 * 3


def test_a_brief_detour_into_a_later_stage_does_not_shrink_the_estimate(tmp_path):
    db = Database(tmp_path / "s.db")
    for stage in Stage:
        db.stages.add(stage, 4.0)
    job = Job(id="j", topic="t")
    job.stage_seconds = {Stage.STARTING: 2.0, Stage.WRITING: 0.5}  # thought once between searches
    job.progress = Progress(Stage.SEARCHING, 2)
    assert runner_over(db).expected_seconds(job) == 2 + 4 + 4 * 3


def test_a_fresh_runner_expects_the_default_time_of_every_stage(tmp_path):
    assert runner_over(Database(tmp_path / "s.db")).expected_seconds(Job(id="j", topic="t")) == sum(DEFAULT_STAGE_SECONDS.values())


def test_a_new_try_clears_only_the_same_persons_failed_job(tmp_path):
    class Failing:
        def generate(self, topic, on_progress=None, exclude=None):
            raise GenerationError("no")

    runner = runner_over(Database(tmp_path / "s.db"))
    mine = runner.start("A", Failing(), created_by=1)
    theirs = runner.start("B", Failing(), created_by=2)
    assert {j.id for j in runner.open()} == {mine.id, theirs.id}
    again = runner.start("A", Failing(), created_by=1)
    assert {j.id for j in runner.open()} == {theirs.id, again.id}


def test_deleting_the_session_while_its_pictures_are_drawn_leaves_no_files(tmp_path):
    db = Database(tmp_path / "s.db")

    class Deleting:
        """Deletes the session as soon as it starts drawing, as a user could from the home page."""

        def expected_seconds(self, count):
            return None

        def paint(self, prompts, on_drawn=None, on_picture=None):
            db.sessions.delete(db.connect().execute("SELECT MAX(id) FROM sessions").fetchone()[0])
            pictures = [Drawn(b"PNG", "m", 1.0) for _ in prompts]
            for i, drawn in enumerate(pictures):
                on_picture(i, drawn)
            return pictures

    files = PictureFiles(tmp_path / "images")
    job = runner_over(db).start("A", Recording(), Illustrator(Deleting(), db.pictures, files))
    assert job.status == "done" and db.sessions.get(job.session_id) is None
    assert list(files.dir.iterdir()) == []


def figure(after: int, url: str = "https://news.example/tram.jpg") -> FigureDraft:
    return FigureDraft(after=after, image_url=url, page_url="https://news.example/trams", credit="Yonhap", caption=f"Under {after}.")


def test_the_cover_goes_under_the_title_the_other_image_under_its_paragraph_and_no_scene_is_drawn(tmp_path):
    from tests.test_illustrator import FakePainter

    db = Database(tmp_path / "s.db")
    painter = FakePainter()
    illustrator = Illustrator(painter, db.pictures, PictureFiles(db.images_dir))
    job = runner_over(db).start("A", Recording([figure(0), figure(3), figure(1, "https://gone.example/a.jpg")]), illustrator)
    article = db.sessions.get(job.session_id).content.article
    assert [(f.paragraph_id, f.source_url, f.credit, f.caption) for f in article.figures] == [
        (None, "https://news.example/trams", "Yonhap", "Under 0."),
        (article.paragraphs[2].id, "https://news.example/trams", "Yonhap", "Under 3."),
    ]
    assert len(painter.prompts) == 2 * len(sample_draft().vocabulary)  # the words' pictures only


def test_with_no_cover_image_the_articles_scene_is_drawn_as_the_cover(tmp_path):
    from tests.test_illustrator import FakePainter

    db = Database(tmp_path / "s.db")
    illustrator = Illustrator(FakePainter(), db.pictures, PictureFiles(db.images_dir))
    job = runner_over(db).start("A", Recording([figure(0, "https://gone.example/a.jpg"), figure(2)]), illustrator)
    article = db.sessions.get(job.session_id).content.article
    photo, drawn = article.figures
    assert photo.paragraph_id == article.paragraphs[1].id
    assert (drawn.paragraph_id, drawn.caption, drawn.source_url, drawn.credit) == (None, "Waiting for the tram.", None, None)
    assert job.progress.pictures_total == 2 * len(sample_draft().vocabulary) + 1


def test_with_only_a_cover_image_the_paragraph_scene_is_drawn_under_its_paragraph(tmp_path):
    from tests.test_illustrator import FakePainter

    db = Database(tmp_path / "s.db")
    illustrator = Illustrator(FakePainter(), db.pictures, PictureFiles(db.images_dir))
    job = runner_over(db).start("A", Recording([figure(0)]), illustrator)
    article = db.sessions.get(job.session_id).content.article
    photo, drawn = article.figures
    assert (photo.paragraph_id, photo.source_url) == (None, "https://news.example/trams")
    assert (drawn.paragraph_id, drawn.caption, drawn.source_url, drawn.credit) == (article.paragraphs[1].id, "Boarding the last tram.", None, None)
    assert job.progress.pictures_total == 2 * len(sample_draft().vocabulary) + 1


def test_with_no_image_at_all_both_scenes_are_drawn_so_the_article_still_shows_two(tmp_path):
    from tests.test_illustrator import FakePainter

    db = Database(tmp_path / "s.db")
    illustrator = Illustrator(FakePainter(), db.pictures, PictureFiles(db.images_dir))
    job = runner_over(db).start("A", Recording([figure(0, "https://gone.example/a.jpg")]), illustrator)
    article = db.sessions.get(job.session_id).content.article
    assert [(f.paragraph_id, f.caption) for f in article.figures] == [(None, "Waiting for the tram."), (article.paragraphs[1].id, "Boarding the last tram.")]
    assert job.progress.pictures_total == 2 * len(sample_draft().vocabulary) + 2


def test_two_images_that_both_ask_for_a_paragraph_also_fill_the_cover_so_nothing_is_drawn(tmp_path):
    from tests.test_illustrator import FakePainter

    db = Database(tmp_path / "s.db")
    painter = FakePainter()
    illustrator = Illustrator(painter, db.pictures, PictureFiles(db.images_dir))
    job = runner_over(db).start("A", Recording([figure(1), figure(2)]), illustrator)
    article = db.sessions.get(job.session_id).content.article
    assert [(f.paragraph_id, f.caption) for f in article.figures] == [(article.paragraphs[0].id, "Under 1."), (None, "Under 2.")]
    assert len(painter.prompts) == 2 * len(sample_draft().vocabulary)  # the words' pictures only


def test_an_article_stops_at_two_images_however_many_the_generator_names(tmp_path):
    db = Database(tmp_path / "s.db")
    job = runner_over(db).start("A", Recording([figure(0), figure(3), figure(1)]))
    article = db.sessions.get(job.session_id).content.article
    assert [f.caption for f in article.figures] == ["Under 0.", "Under 3."]


def test_an_article_keeps_one_cover_and_a_second_goes_under_the_first_paragraph(tmp_path):
    db = Database(tmp_path / "s.db")
    job = runner_over(db).start("A", Recording([figure(0), figure(0, "https://news.example/b.jpg")]))
    article = db.sessions.get(job.session_id).content.article
    assert [f.paragraph_id for f in article.figures] == [None, article.paragraphs[0].id]


def test_a_source_image_comes_through_with_pictures_off_and_a_late_paragraph_number_lands_on_the_last(tmp_path):
    db = Database(tmp_path / "s.db")
    job = runner_over(db).start("A", Recording([figure(9)]))
    article = db.sessions.get(job.session_id).content.article
    assert [f.paragraph_id for f in article.figures] == [article.paragraphs[-1].id]
    assert PictureFiles(db.images_dir).path(int(article.figures[0].image.removesuffix(".png"))).is_file()


def test_a_job_picks_by_what_its_starter_has_seen(tmp_path):
    db = Database(tmp_path / "s.db")
    ids = seed_expressions(db, EXPRESSION_COUNT + 1)
    me, other = add_user(db, "me@example.com"), add_user(db, "other@example.com")
    theirs = sample_draft()
    theirs.vocabulary[0] = theirs.vocabulary[0].model_copy(update={"word": "theirs"})
    db.sessions.create(theirs, [ids[1]], created_by=other.id)
    db.sessions.create(sample_draft(), [ids[0]], created_by=me.id)
    generator = Recording()
    job = runner_over(db).start("A", generator, created_by=me.id)
    session = db.sessions.get(job.session_id)
    assert {e.id for e in session.content.expressions} == set(ids) - {ids[0]}
    assert "theirs" not in generator.excluded[0].words
    assert db.shares.created_by(session.id) == me.id


class Exploding:
    def generate(self, topic, on_progress=None, exclude=None):
        raise RuntimeError("no network")


def test_a_job_that_dies_of_anything_is_failed_and_reported(tmp_path):
    db = Database(tmp_path / "s.db")
    finished = []
    job = runner_over(db).start("Trams", Exploding(), on_finished=finished.append)
    assert job.status == "failed" and "no network" in job.error
    assert finished == [job]


def test_a_failure_the_generator_reports_is_reported_too(tmp_path):
    db = Database(tmp_path / "s.db")
    finished = []

    class Failing:
        def generate(self, topic, on_progress=None, exclude=None):
            raise GenerationError("claude exited 1")

    job = runner_over(db).start("Trams", Failing(), on_finished=finished.append)
    assert job.status == "failed" and finished == [job]


class Draws:
    """Stands in for the illustrator: `during` runs while it draws, then it fails or reports what did not come back."""

    def __init__(self, missing=0, error=None, during=None):
        self.missing, self.error, self.during = missing, error, during

    def expected_seconds(self, count):
        return None

    def count(self, words, scenes):
        return 1

    def illustrate(self, job_id, words, on_done, on_picture, scenes, on_figure):
        if self.during:
            self.during(job_id, on_picture)
        on_done(1)
        if self.error:
            raise self.error
        return self.missing


def test_every_finished_job_is_reported_once(tmp_path):
    db = Database(tmp_path / "s.db")
    finished = []
    job = runner_over(db).start("Trams", Recording(), on_finished=finished.append)
    assert job.status == "done" and job.spent is True and finished == [job]


def test_a_job_cancelled_in_the_queue_calls_nothing_and_has_spent_nothing(tmp_path):
    db = Database(tmp_path / "s.db")

    class Queue:
        def submit(self, fn, /, *args):
            self.waiting = (fn, args)

    queue = Queue()
    runner = JobRunner(db.sessions, db.expressions, db.stages, queue)
    generator, finished = Recording(), []
    job = runner.start("Trams", generator, on_finished=finished.append)
    runner.close(job.id)
    fn, args = queue.waiting
    fn(*args)
    assert job.status == "cancelled" and job.spent is False
    assert generator.excluded == [] and finished == [job]


def test_a_cancel_before_the_session_is_saved_has_spent_claude(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    finished = []

    class CancelsItself:
        """With InlineExecutor the job runs inside start(), so the one open job is this one."""

        def generate(self, topic, on_progress=None, exclude=None):
            runner.close(runner.open()[0].id)
            on_progress(Progress(Stage.SEARCHING, 1))  # raises Cancelled
            return sample_draft()

    job = runner.start("Trams", CancelsItself(), on_finished=finished.append)
    assert job.status == "cancelled" and job.session_id is None and job.spent is True
    assert finished == [job]


def test_a_cancel_the_generator_never_hears_of_saves_nothing(tmp_path):
    db = Database(tmp_path / "s.db")
    runner = runner_over(db)

    class FinishesAnyway:
        def generate(self, topic, on_progress=None, exclude=None):
            runner.close(runner.open()[0].id)
            return sample_draft()

    job = runner.start("Trams", FinishesAnyway())
    assert job.status == "cancelled" and job.session_id is None


def test_a_cancel_while_the_pictures_are_drawn_deletes_the_session_and_its_files(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    files = PictureFiles(db.images_dir)
    finished, saved = [], {}

    def landing_then_cancelling(job_id, on_picture):
        picture_id = db.pictures.add(None, None, None)
        files.write(picture_id, b"PNG")
        on_picture(0, "example_image", picture_id)
        saved["session"] = runner.get(job_id).session_id
        runner.close(job_id)

    job = runner.start("Trams", Recording(), Draws(during=landing_then_cancelling), on_finished=finished.append)
    assert job.status == "cancelled" and job.session_id is None and job.spent is True
    assert db.sessions.get(saved["session"]) is None
    assert list(db.images_dir.iterdir()) == []
    assert finished == [job]


def cancels_while_drawing(runner: JobRunner) -> Draws:
    return Draws(during=lambda job_id, on_picture: runner.close(job_id))


def test_a_busy_moment_does_not_keep_a_cancelled_session(tmp_path, monkeypatch):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    delete = db.sessions.delete
    tries = []

    def busy_at_first(session_id):
        tries.append(session_id)
        if len(tries) == 1:
            raise sqlite3.OperationalError("database is locked")
        return delete(session_id)

    monkeypatch.setattr(db.sessions, "delete", busy_at_first)
    monkeypatch.setattr("app.db.retry.time.sleep", lambda _: None)
    job = runner.start("Trams", Recording(), cancels_while_drawing(runner))
    assert job.status == "cancelled" and job.session_id is None and len(tries) == 2
    assert db.sessions.get(tries[0]) is None


def test_a_cancelled_session_that_will_not_go_stays_named_on_the_job_which_still_ends(tmp_path, monkeypatch):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    finished = []

    def refuses(session_id):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db.sessions, "delete", refuses)
    monkeypatch.setattr("app.db.retry.time.sleep", lambda _: None)
    job = runner.start("Trams", Recording(), cancels_while_drawing(runner), on_finished=finished.append)
    assert job.status == "cancelled" and job.session_id is not None and finished == [job]
    assert db.sessions.get(job.session_id) is not None


def test_a_picture_file_that_will_not_go_does_not_stop_a_cancelled_job_ending(tmp_path, monkeypatch):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    files = PictureFiles(db.images_dir)
    finished = []

    def landing_then_cancelling(job_id, on_picture):
        picture_id = db.pictures.add(None, None, None)
        files.write(picture_id, b"PNG")
        on_picture(0, "example_image", picture_id)
        runner.close(job_id)

    def refuses(picture_id):
        raise OSError("Read-only file system")

    monkeypatch.setattr(runner._sources, "drop", refuses)
    job = runner.start("Trams", Recording(), Draws(during=landing_then_cancelling), on_finished=finished.append)
    assert job.status == "cancelled" and job.session_id is None and finished == [job]


def test_a_cancel_after_the_last_progress_report_still_counts(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)

    class CancelsLast(Draws):
        def illustrate(self, job_id, words, on_done, on_picture, scenes, on_figure):
            on_done(1)
            runner.close(job_id)
            return 0

    job = runner.start("Trams", Recording(), CancelsLast())
    assert job.status == "cancelled" and job.session_id is None


def test_a_job_that_dies_after_its_session_is_saved_is_failed_and_keeps_it(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    finished = []
    job = runner_over(db).start("Trams", Recording(), Draws(error=OSError("No space left on device")), on_finished=finished.append)
    assert job.status == "failed" and "No space left" in job.error
    assert job.session_id is not None and db.sessions.get(job.session_id) is not None
    assert finished == [job]


@pytest.mark.parametrize(
    "draws,missing",
    [(Draws(), False), (Draws(missing=2), True), (Draws(error=GenerationError("openrouter down")), True)],
)
def test_a_job_knows_whether_every_picture_came_back(tmp_path, draws, missing):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    job = runner_over(db).start("Trams", Recording(), draws)
    assert job.status == "done" and job.pictures_missing is missing


def test_drawing_names_only_a_running_job_that_saved_that_session(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    seen = {}

    def look(job_id, on_picture):
        sid = runner.get(job_id).session_id
        seen.update(sid=sid, during=runner.drawing(sid), other=runner.drawing(sid + 1))

    runner.start("Trams", Recording(), Draws(during=look))
    assert seen["during"] is True and seen["other"] is False
    assert runner.drawing(seen["sid"]) is False


def test_telling_of_the_end_can_fail_without_taking_the_job_down(tmp_path):
    db = Database(tmp_path / "s.db")

    def refuses(job):
        raise RuntimeError("database is locked")

    job = runner_over(db).start("Trams", Exploding(), on_finished=refuses)
    assert job.status == "failed"


class ShutDown:
    """An executor as it is once the server has begun to stop."""

    def submit(self, fn, /, *args):
        raise RuntimeError("cannot schedule new futures after shutdown")


def test_a_job_the_executor_refuses_is_failed_and_reported(tmp_path):
    db = Database(tmp_path / "s.db")
    finished = []
    job = JobRunner(db.sessions, db.expressions, db.stages, ShutDown()).start("Trams", Recording(), on_finished=finished.append)
    assert job.status == "failed" and "shutdown" in job.error
    assert finished == [job]
