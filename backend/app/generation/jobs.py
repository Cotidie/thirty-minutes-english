"""Background generation jobs with observable progress, kept in memory."""

import logging
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from statistics import median
from threading import Lock
from typing import Literal, NamedTuple, Protocol

from app.db.expressions import ExpressionRepo
from app.db.sessions import SessionRepo
from app.db.stages import StageRepo
from app.generation.exclusions import Exclusions
from app.generation.generator import VOCABULARY_COUNT, Generator
from app.generation.progress import Progress, Stage, with_pictures
from app.llm import GenerationError
from app.models import ArticleDraft, FigureDraft, PictureDraft, Session
from app.pictures.figures import SourceImages
from app.pictures.illustrator import Illustrator

Status = Literal["running", "done", "failed", "cancelled"]
log = logging.getLogger(__name__)

# How many corpus expressions a session teaches.
EXPRESSION_COUNT = 5

# How many images an article shows: its cover and one under a paragraph.
ARTICLE_IMAGES = 2

# Seconds per stage before any run has finished; a stage a run skips counts as 0.
DEFAULT_STAGE_SECONDS: dict[Stage, float] = {
    Stage.STARTING: 10,
    Stage.SKILLS: 10,
    Stage.SEARCHING: 40,
    Stage.WRITING: 100,
    Stage.FINALIZING: 10,
    Stage.ILLUSTRATING: 90,
}


class ArticleScene(NamedTuple):
    """A scene to draw for the article, and the paragraph it lands under: None for the cover."""

    picture: PictureDraft
    paragraph: int | None


class Cancelled(Exception):
    """Raised from a progress callback once the job is cancelled, to unwind the worker."""


@dataclass
class Job:
    id: str
    topic: str
    started_at: float = field(default_factory=time.monotonic)
    stage_started_at: float = field(default_factory=time.monotonic)
    status: Status = "running"
    progress: Progress = field(default_factory=lambda: Progress(Stage.STARTING))
    stage_seconds: dict[Stage, float] = field(default_factory=dict)  # time in each stage left so far, summed over visits
    foreseen: dict[Stage, float] = field(default_factory=dict)  # what this job's own setup says a stage takes
    session_id: int | None = None
    created_by: int | None = None
    error: str | None = None
    failed_at: float | None = None  # stops the clock, so the failure keeps its time while it waits to be read

    @property
    def stage(self) -> Stage:
        return self.progress.stage

    def apply(self, progress: Progress) -> None:
        if self.status == "cancelled":
            raise Cancelled
        if progress.stage != self.stage:
            self.finish()
            self.stage_started_at = time.monotonic()
        self.progress = progress

    def cancel(self) -> None:
        if self.status == "running":
            self.status = "cancelled"

    def finish(self) -> None:
        """Books the current visit's time to its stage; the model can go back, e.g. think between searches."""
        self.stage_seconds[self.stage] = self.stage_seconds.get(self.stage, 0.0) + self.stage_elapsed_seconds

    @property
    def elapsed_seconds(self) -> float:
        return (self.failed_at or time.monotonic()) - self.started_at

    @property
    def stage_elapsed_seconds(self) -> float:
        return time.monotonic() - self.stage_started_at


class Executor(Protocol):
    def submit(self, fn, /, *args): ...


class JobRunner:
    REPEAT_ALLOWANCE = 0.1  # each past word escapes the exclusion list with this probability

    def __init__(
        self,
        sessions: SessionRepo,
        expressions: ExpressionRepo,
        stages: StageRepo,
        executor: Executor | None = None,
        sources: SourceImages | None = None,
    ) -> None:
        """`sources` downloads the images the generator found; without it the article gets only a drawn picture."""
        self._sessions = sessions
        self._expressions = expressions
        self._stages = stages
        self._sources = sources
        self.executor = executor or ThreadPoolExecutor(max_workers=2)
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def start(self, topic: str, generator: Generator, illustrator: Illustrator | None = None, created_by: int | None = None) -> Job:
        """Generates in the background; the pictures follow when an illustrator is given."""
        job = Job(id=uuid.uuid4().hex[:12], topic=topic, created_by=created_by)
        self._foresee_pictures(job, illustrator, 2 * VOCABULARY_COUNT)  # the example and the scene
        with self._lock:
            # A new try answers the same person's old failure.
            self._jobs = {id: j for id, j in self._jobs.items() if j.status != "failed" or j.created_by != created_by}
            self._jobs[job.id] = job
        self.executor.submit(self._run, job, generator, illustrator)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def open(self) -> list[Job]:
        """Jobs the user still has to see, oldest first: the running ones, and failures not yet closed."""
        with self._lock:
            return [job for job in self._jobs.values() if job.status in ("running", "failed")]

    def close(self, job_id: str) -> Job | None:
        """Cancels a running job; forgets a failed one, whose error the user has now read."""
        job = self.get(job_id)
        if job and job.status == "failed":
            with self._lock:
                self._jobs.pop(job_id, None)
        elif job:
            job.cancel()
        return job

    def stage_expected_seconds(self, stage: Stage, job: Job | None = None) -> float:
        """What `job`'s own setup foresees (its picture model's time here), else the latest runs' median."""
        if job and stage in job.foreseen:
            return job.foreseen[stage]
        history = self._stages.recent(stage)
        return median(history) if history else DEFAULT_STAGE_SECONDS[stage]

    def expected_seconds(self, job: Job) -> float:
        """Earlier stages as they took; the current and later ones at least as long as they usually take."""
        order = list(Stage)
        total = 0.0
        for stage in Stage:
            spent = job.stage_seconds.get(stage, 0.0) + (job.stage_elapsed_seconds if stage == job.stage else 0.0)
            ahead = order.index(stage) >= order.index(job.stage)
            total += max(spent, self.stage_expected_seconds(stage, job)) if ahead else spent
        return total

    def _run(self, job: Job, generator: Generator, illustrator: Illustrator | None) -> None:
        """The session is saved, with expressions from the corpus, and `job.session_id` set, as soon as
        its text is written; the pictures land on it one by one after that, so it can be opened while they are drawn."""
        try:
            used = Exclusions(self._sessions.used_words(seen_by=job.created_by))
            exclude = used.thin(1 - self.REPEAT_ALLOWANCE, random.Random())
            log.info("job %s: banning %d/%d words", job.id, len(exclude.words), len(used.words))
            draft = generator.generate(job.topic, on_progress=job.apply, exclude=exclude)
            leaked = exclude.taught([v.word for v in draft.vocabulary])
            if leaked:
                log.warning("job %s: %d banned words came back anyway: %s", job.id, len(leaked), leaked)
            if job.status == "cancelled":
                return
            picked = self._expressions.pick(EXPRESSION_COUNT, random.Random(), seen_by=job.created_by)
            session = self._sessions.create(draft, [e.id for e in picked], job.created_by)
            job.session_id = session.id
            landed = self._keep_figures(session, draft.article.figures)
            if illustrator:
                self._illustrate(job, illustrator, session, self._scenes_to_draw(session, draft.article, landed))
        except Cancelled:
            log.info("job %s: cancelled", job.id)
            return
        except GenerationError as e:
            if job.status == "cancelled":
                return
            job.error = str(e)
            job.failed_at = time.monotonic()
            job.status = "failed"
            log.warning("job %s: failed after %.0fs in %s: %s", job.id, job.elapsed_seconds, job.stage, e)
            return
        job.finish()
        for stage in Stage:
            self._stages.add(stage, job.stage_seconds.get(stage, 0.0))
        log.info("job %s: done in %.0fs: %s", job.id, job.elapsed_seconds, {s.value: round(t) for s, t in job.stage_seconds.items()})
        job.status = "done"

    @staticmethod
    def _foresee_pictures(job: Job, illustrator: Illustrator | None, count: int) -> None:
        seconds = illustrator.expected_seconds(count) if illustrator else None
        if seconds is not None:
            job.foreseen[Stage.ILLUSTRATING] = seconds

    @staticmethod
    def _under(session: Session, after: int) -> int:
        """The id of paragraph `after` (counted from 1), the last one when the number runs past them."""
        paragraphs = session.content.article.paragraphs
        return paragraphs[min(max(after, 1), len(paragraphs)) - 1].id

    def _place(self, session: Session, after: int, landed: list[int | None]) -> int | None:
        """Where the next image goes: the place it asks for (after 0 is the cover), or the other when that one is taken."""
        cover_taken = None in landed
        paragraph_taken = any(paragraph is not None for paragraph in landed)
        takes_cover = not cover_taken if after == 0 else paragraph_taken
        return None if takes_cover else self._under(session, after)

    def _keep_figures(self, session: Session, figures: list[FigureDraft]) -> list[int | None]:
        """Downloads the images the generator found until the article has its two, one under the title as the cover
        and one under its paragraph. Where each kept one landed: its paragraph's id, None for the cover."""
        if self._sources is None or not session.content.article.paragraphs:
            return []
        landed: list[int | None] = []
        for figure in figures:
            if len(landed) == ARTICLE_IMAGES:
                break
            picture_id = self._sources.keep(figure.image_url)
            if picture_id is None:
                continue
            paragraph = self._place(session, figure.after, landed)
            try:
                self._sessions.add_figure(session.id, paragraph, picture_id, figure.caption, figure.page_url or None, figure.credit or None)
            except KeyError:
                self._sources.drop(picture_id)
                return landed
            landed.append(paragraph)
        return landed

    def _scenes_to_draw(self, session: Session, article: ArticleDraft, landed: list[int | None]) -> list[ArticleScene]:
        """What the kept images leave the article short of, so that it shows its two: a cover, one under a paragraph."""
        if not session.content.article.paragraphs:
            return []
        scenes: list[ArticleScene] = []
        if article.picture and None not in landed:
            scenes.append(ArticleScene(article.picture, None))
        if article.paragraph_picture and all(paragraph is None for paragraph in landed):
            scenes.append(ArticleScene(article.paragraph_picture, self._under(session, article.paragraph_picture.after)))
        return scenes

    def _illustrate(self, job: Job, illustrator: Illustrator, session: Session, scenes: list[ArticleScene]) -> None:
        """Each picture onto the saved session as it is drawn, the article's `scenes` among them;
        a painter failure leaves the session without the rest."""
        words = session.content.vocabulary
        article_scenes = [scene.picture.scene for scene in scenes]
        total = illustrator.count(words, article_scenes)
        self._foresee_pictures(job, illustrator, total)
        job.apply(with_pictures(job.progress, 0, total))
        try:
            illustrator.illustrate(
                job.id,
                words,
                lambda done: job.apply(with_pictures(job.progress, done, total)),
                lambda index, field, picture_id: self._sessions.replace_picture(words[index].id, field, picture_id),
                article_scenes,
                lambda n, picture_id: self._sessions.add_figure(session.id, scenes[n].paragraph, picture_id, scenes[n].picture.caption, None, None),
            )
        except GenerationError as e:
            log.warning("job %s: the session stays without the pictures not yet drawn: %s", job.id, e)
