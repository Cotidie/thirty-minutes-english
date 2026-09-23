from fastapi import APIRouter, HTTPException, Response

from app.api.deps import Db, Jobs, Svc, failed, off, require_session
from app.api.schemas import CreateSessionRequest, JobStatus, RedrawRequest
from app.claude_cli import GenerationError
from app.generation.jobs import Job, JobRunner
from app.models import Session, SessionSummary, Stars, VocabularyItem
from app.topics.pool import pick_topic

router = APIRouter(prefix="/api")

RECENT_TOPIC_WINDOW = 10


def status_of(job: Job, runner: JobRunner) -> JobStatus:
    return JobStatus(
        id=job.id,
        topic=job.topic,
        status=job.status,
        stage=job.stage,
        searches=job.searches,
        elapsed_seconds=job.elapsed_seconds,
        stage_elapsed_seconds=job.stage_elapsed_seconds,
        expected_seconds=runner.expected_seconds(),
        session_id=job.session_id,
        error=job.error,
    )


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(db: Db) -> list[SessionSummary]:
    return db.sessions.list_all()


@router.post("/sessions", response_model=JobStatus, status_code=202)
def create_session(body: CreateSessionRequest, db: Db, jobs: Jobs, services: Svc) -> JobStatus:
    """A blank topic takes one from the pool that the last few sessions did not use."""
    topic = (body.topic or "").strip() or pick_topic(db.sessions.recent_topics(RECENT_TOPIC_WINDOW))
    return status_of(jobs.start(topic, services.generator, services.illustrator), jobs)


@router.get("/jobs", response_model=list[JobStatus])
def list_running_jobs(jobs: Jobs) -> list[JobStatus]:
    return [status_of(job, jobs) for job in jobs.running()]


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str, jobs: Jobs) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return status_of(job, jobs)


@router.get("/sessions/{session_id}", response_model=Session)
def get_session(session_id: int, db: Db) -> Session:
    session = db.sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, db: Db) -> Response:
    if not db.sessions.delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


@router.post("/sessions/{session_id}/pictures/{index}", response_model=VocabularyItem)
def redraw_picture(session_id: int, index: int, body: RedrawRequest, db: Db, services: Svc) -> VocabularyItem:
    """A fresh scene for one word, drawn and saved in place of the old picture."""
    session = db.sessions.get(session_id)
    if session is None or not 0 <= index < len(session.content.vocabulary):
        raise HTTPException(status_code=404, detail="no such word")
    illustrator, writer = services.illustrator, services.scene_writer
    if illustrator is None or writer is None:
        raise off("pictures are off: set IMAGE_PROVIDER and its key in Settings")
    item = session.content.vocabulary[index]
    try:
        drawn = illustrator.redraw(session_id, index, item, writer.write(item), body.style)
    except GenerationError as e:
        raise failed("redraw", e) from e
    previous = db.sessions.replace_vocabulary_item(session_id, index, drawn)
    if previous is None:
        raise HTTPException(status_code=404, detail="the session went away while drawing")
    if previous.image != drawn.image:
        illustrator.discard(previous.image)
    return drawn


@router.get("/sessions/{session_id}/stars", response_model=Stars)
def get_stars(session_id: int, db: Db) -> Stars:
    require_session(db, session_id)
    return db.sessions.get_stars(session_id)


@router.put("/sessions/{session_id}/stars", response_model=Stars)
def set_stars(session_id: int, body: Stars, db: Db) -> Stars:
    require_session(db, session_id)
    return db.sessions.set_stars(session_id, body)
