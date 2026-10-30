from io import BytesIO

import httpx2
from PIL import Image as PILImage

from app.db import Database
from app.models import FigureDraft
from app.pictures.figures import SourceImages
from app.pictures.files import PictureFiles
from app.pictures.illustrator import Illustrator
from app.pictures.painters import Drawn
from app.generation.jobs import DEFAULT_STAGE_SECONDS, EXPRESSION_COUNT, Job, JobRunner
from app.generation.progress import Progress, Stage
from tests.conftest import sample_draft, seed_expressions


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


def test_deleting_the_session_while_its_pictures_are_drawn_leaves_no_files(tmp_path):
    db = Database(tmp_path / "s.db")

    class Deleting:
        """Deletes the session as soon as it starts drawing, as a user could from the home page."""

        def expected_seconds(self, count):
            return None

        def paint(self, prompts, on_drawn=None, on_picture=None):
            db.sessions.delete(db.sessions.list_all()[0].id)
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
