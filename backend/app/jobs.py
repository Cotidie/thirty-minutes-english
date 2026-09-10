"""Background generation jobs with observable progress, kept in memory."""

import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from statistics import median
from threading import Lock
from typing import Literal, Protocol

from app.generator import GenerationError, Generator
from app.progress import Progress, Stage
from app.store import SessionStore

Status = Literal["running", "done", "failed"]


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

    def __init__(
        self, generator: Generator, store: SessionStore, executor: Executor | None = None
    ) -> None:
        self._generator = generator
        self._store = store
        self._executor = executor or ThreadPoolExecutor(max_workers=2)
        self._jobs: dict[str, Job] = {}
        self._durations: deque[float] = deque(maxlen=5)
        self._lock = Lock()

    def start(self, topic: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], topic=topic)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def expected_seconds(self) -> float:
        with self._lock:
            return median(self._durations) if self._durations else self.DEFAULT_EXPECTED_SECONDS

    def _run(self, job: Job) -> None:
        try:
            content = self._generator.generate(job.topic, on_progress=job.apply)
        except GenerationError as e:
            job.error = str(e)
            job.status = "failed"
            return
        session = self._store.create(content)
        with self._lock:
            self._durations.append(job.elapsed_seconds)
        job.session_id = session.id
        job.status = "done"
