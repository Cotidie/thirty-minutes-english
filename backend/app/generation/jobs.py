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

from app.claude_cli import GenerationError
from app.db.sessions import SessionRepo
from app.generation.generator import Generator
from app.generation.progress import Progress, Stage
from app.pictures.illustrator import Illustrator

Status = Literal["running", "done", "failed"]
log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    topic: str
    started_at: float = field(default_factory=time.monotonic)
    stage_started_at: float = field(default_factory=time.monotonic)
    status: Status = "running"
    stage: Stage = Stage.STARTING
    searches: int = 0
    session_id: int | None = None
    error: str | None = None

    def apply(self, progress: Progress) -> None:
        if progress.stage != self.stage:
            self.stage_started_at = time.monotonic()
        self.stage = progress.stage
        self.searches = progress.searches

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def stage_elapsed_seconds(self) -> float:
        return time.monotonic() - self.stage_started_at


class Executor(Protocol):
    def submit(self, fn, /, *args): ...


class JobRunner:
    DEFAULT_EXPECTED_SECONDS = 150.0
    REPEAT_ALLOWANCE = 0.1  # each past item escapes the exclusion list with this probability

    def __init__(self, sessions: SessionRepo, executor: Executor | None = None) -> None:
        self._sessions = sessions
        self.executor = executor or ThreadPoolExecutor(max_workers=2)
        self._jobs: dict[str, Job] = {}
        self._durations: deque[float] = deque(maxlen=5)
        self._lock = Lock()

    def start(self, topic: str, generator: Generator, illustrator: Illustrator | None = None) -> Job:
        """Generates in the background; the pictures follow when an illustrator is given."""
        job = Job(id=uuid.uuid4().hex[:12], topic=topic)
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

    def expected_seconds(self) -> float:
        with self._lock:
            return median(self._durations) if self._durations else self.DEFAULT_EXPECTED_SECONDS

    def _run(self, job: Job, generator: Generator, illustrator: Illustrator | None) -> None:
        try:
            used = self._sessions.used_items()
            exclude = used.thin(1 - self.REPEAT_ALLOWANCE, random.Random())
            log.info("job %s: banning %d/%d expressions, %d/%d words", job.id,
                     len(exclude.expressions), len(used.expressions), len(exclude.words), len(used.words))
            content = generator.generate(job.topic, on_progress=job.apply, exclude=exclude)
        except GenerationError as e:
            job.error = str(e)
            job.status = "failed"
            return
        leaked = sorted(
            {e.phrase for e in content.expressions} & set(exclude.expressions)
            | {v.word for v in content.vocabulary} & set(exclude.words)
        )
        if leaked:
            log.warning("job %s: %d banned items came back anyway: %s", job.id, len(leaked), leaked)
        if illustrator:
            job.apply(Progress(Stage.ILLUSTRATING, job.searches))
            try:
                content = illustrator.illustrate(job.id, content)
            except GenerationError as e:
                log.warning("job %s: the session goes out without pictures: %s", job.id, e)
        session = self._sessions.create(content)
        with self._lock:
            self._durations.append(job.elapsed_seconds)
        job.session_id = session.id
        job.status = "done"
