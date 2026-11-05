"""Which job a log line belongs to, so the lines of two generations running at once can be told apart."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_JOB: ContextVar[str] = ContextVar("job", default="")

# The app's log line: "INFO app.llm job 3f2a9c1b07de: opus run (editing): 229.8s, ..." inside a job.
LOG_FORMAT = "%(levelname)s %(name)s%(job)s: %(message)s"


@contextmanager
def job_logs(job_id: str) -> Iterator[None]:
    """Lines logged inside, on this thread and the event loops it runs, name `job_id`."""
    token = _JOB.set(job_id)
    try:
        yield
    finally:
        _JOB.reset(token)


class JobTag(logging.Filter):
    """Gives every record a `job` field: " job <id>" inside a job, else blank, for a format's `%(job)s`."""

    def filter(self, record: logging.LogRecord) -> bool:
        job = _JOB.get()
        record.job = f" job {job}" if job else ""
        return True


def tag_job_logs(handlers: list[logging.Handler]) -> None:
    """Puts the job tag on `handlers`, so a format that names `%(job)s` always finds it."""
    for handler in handlers:
        handler.addFilter(JobTag())
