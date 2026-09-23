"""Background generation jobs with observable progress, kept in memory."""

import logging
import random
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from statistics import median
from threading import Lock
from typing import Literal, Protocol

from app.db.sessions import SessionRepo
from app.generation.generator import VOCABULARY_COUNT, Generator
from app.generation.progress import Progress, Stage, with_pictures
from app.llm import GenerationError
from app.models import SessionContent
from app.pictures.illustrator import Illustrator

Status = Literal["running", "done", "failed", "cancelled"]
log = logging.getLogger(__name__)

# Seconds per stage before any run has finished; a stage a run skips counts as 0.
DEFAULT_STAGE_SECONDS: dict[Stage, float] = {
    Stage.STARTING: 10,
    Stage.SKILLS: 10,
    Stage.SEARCHING: 40,
    Stage.WRITING: 100,
    Stage.FINALIZING: 10,
    Stage.ILLUSTRATING: 90,
}


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
    error: str | None = None

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
        return time.monotonic() - self.started_at

    @property
    def stage_elapsed_seconds(self) -> float:
        return time.monotonic() - self.stage_started_at


class Executor(Protocol):
    def submit(self, fn, /, *args): ...


class JobRunner:
    REPEAT_ALLOWANCE = 0.1  # each past item escapes the exclusion list with this probability

    def __init__(self, sessions: SessionRepo, executor: Executor | None = None) -> None:
        self._sessions = sessions
        self.executor = executor or ThreadPoolExecutor(max_workers=2)
        self._jobs: dict[str, Job] = {}
        self._stage_history: dict[Stage, deque[float]] = {stage: deque(maxlen=5) for stage in Stage}
        self._lock = Lock()

    def start(self, topic: str, generator: Generator, illustrator: Illustrator | None = None) -> Job:
        """Generates in the background; the pictures follow when an illustrator is given."""
        job = Job(id=uuid.uuid4().hex[:12], topic=topic)
        self._foresee_pictures(job, illustrator, VOCABULARY_COUNT)
        with self._lock:
            self._jobs[job.id] = job
        self.executor.submit(self._run, job, generator, illustrator)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> list[Job]:
        """Unfinished jobs, oldest first."""
        with self._lock:
            return [job for job in self._jobs.values() if job.status == "running"]

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job:
            job.cancel()
        return job

    def stage_expected_seconds(self, stage: Stage, job: Job | None = None) -> float:
        """What `job`'s own setup foresees (its picture model's time here), else the latest runs' median."""
        if job and stage in job.foreseen:
            return job.foreseen[stage]
        with self._lock:
            history = self._stage_history[stage]
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
        try:
            used = self._sessions.used_items()
            exclude = used.thin(1 - self.REPEAT_ALLOWANCE, random.Random())
            log.info("job %s: banning %d/%d expressions, %d/%d words", job.id,
                     len(exclude.expressions), len(used.expressions), len(exclude.words), len(used.words))
            content = generator.generate(job.topic, on_progress=job.apply, exclude=exclude)
            if illustrator:
                content = self._illustrate(job, illustrator, content)
        except Cancelled:
            log.info("job %s: cancelled", job.id)
            return
        except GenerationError as e:
            if job.status == "cancelled":
                return
            job.error = str(e)
            job.status = "failed"
            return
        leaked = exclude.taught([e.phrase for e in content.expressions], [v.word for v in content.vocabulary])
        if leaked:
            log.warning("job %s: %d banned items came back anyway: %s", job.id, len(leaked), leaked)
        if job.status == "cancelled":
            return
        session = self._sessions.create(content)
        job.finish()
        with self._lock:
            for stage in Stage:
                self._stage_history[stage].append(job.stage_seconds.get(stage, 0.0))
        job.session_id = session.id
        job.status = "done"

    @staticmethod
    def _foresee_pictures(job: Job, illustrator: Illustrator | None, count: int) -> None:
        seconds = illustrator.expected_seconds(count) if illustrator else None
        if seconds is not None:
            job.foreseen[Stage.ILLUSTRATING] = seconds

    def _illustrate(self, job: Job, illustrator: Illustrator, content: SessionContent) -> SessionContent:
        """Pictures on the words; a painter failure sends the session out without them."""
        total = sum(1 for item in content.vocabulary if item.scene)
        self._foresee_pictures(job, illustrator, total)
        job.apply(with_pictures(job.progress, 0, total))
        try:
            return illustrator.illustrate(job.id, content, lambda done: job.apply(with_pictures(job.progress, done, total)))
        except GenerationError as e:
            log.warning("job %s: the session goes out without pictures: %s", job.id, e)
            return content
