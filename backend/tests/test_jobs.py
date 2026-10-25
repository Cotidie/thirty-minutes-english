from app.db import Database
from app.generation.jobs import DEFAULT_STAGE_SECONDS, EXPRESSION_COUNT, Job, JobRunner
from app.generation.progress import Progress, Stage
from tests.conftest import sample_draft, seed_expressions


class InlineExecutor:
    def submit(self, fn, /, *args):
        fn(*args)


class Recording:
    """A generator that hands back the sample draft and keeps what it was told to avoid."""

    def __init__(self) -> None:
        self.excluded = []

    def generate(self, topic, on_progress=None, exclude=None):
        self.excluded.append(exclude)
        if on_progress:
            on_progress(Progress(Stage.SEARCHING, 1))
        return sample_draft(topic=topic)


def runner_over(db: Database) -> JobRunner:
    return JobRunner(db.sessions, db.expressions, db.stages, InlineExecutor())


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
