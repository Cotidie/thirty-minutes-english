from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import Db, Files, Jobs, Svc, failed, off, require_session
from app.api.schemas import CreateSessionRequest, JobStatus, RedrawRequest
from app.generation.jobs import Job, JobRunner
from app.llm import GenerationError
from app.models import Note, Session, SessionSummary, Stars, VocabularyItem
from app.topics.pool import pick_topic

router = APIRouter(prefix="/api")

RECENT_TOPIC_WINDOW = 10


def status_of(job: Job, runner: JobRunner) -> JobStatus:
    return JobStatus(
        id=job.id,
        topic=job.topic,
        status=job.status,
        **asdict(job.progress),
        elapsed_seconds=job.elapsed_seconds,
        stage_elapsed_seconds=job.stage_elapsed_seconds,
        stage_expected_seconds=runner.stage_expected_seconds(job.stage, job),
        expected_seconds=runner.expected_seconds(job),
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
def list_open_jobs(jobs: Jobs) -> list[JobStatus]:
    """Running jobs, and failed ones until they are closed, so a reload still shows what went wrong."""
    return [status_of(job, jobs) for job in jobs.open()]


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str, jobs: Jobs) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return status_of(job, jobs)


@router.delete("/jobs/{job_id}", response_model=JobStatus)
def close_job(job_id: str, jobs: Jobs) -> JobStatus:
    """Stops a running job: the worker quits at its next progress report and saves nothing. Dismisses a failed one."""
    job = jobs.close(job_id)
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
def delete_session(session_id: int, db: Db, files: Files) -> Response:
    """The session, everything kept with it, and the picture files its words showed."""
    pictures = db.sessions.delete(session_id)
    if pictures is None:
        raise HTTPException(status_code=404, detail="session not found")
    for picture_id in pictures:
        files.remove(picture_id)
    return Response(status_code=204)


@router.post("/sessions/{session_id}/pictures/{index}", response_model=VocabularyItem)
def redraw_picture(session_id: int, index: int, body: RedrawRequest, db: Db, services: Svc, files: Files) -> VocabularyItem:
    """One of a word's pictures drawn again and shown in place of the old one, whose file goes:
    the example sentence as it is, or a fresh scene for Practice."""
    session = db.sessions.get(session_id)
    if session is None or not 0 <= index < len(session.content.vocabulary):
        raise HTTPException(status_code=404, detail="no such word")
    illustrator, writer = services.illustrator, services.scene_writer
    if illustrator is None or writer is None:
        raise off("pictures are off: set IMAGE_PROVIDER and its key in Settings")
    item = session.content.vocabulary[index]
    try:
        if body.face == "example":
            field, scene = "example_image", None
            picture_id = illustrator.redraw_example(item, body.style)
        else:
            field, scene = "image", writer.write(item)
            picture_id = illustrator.redraw(scene, body.style)
    except GenerationError as e:
        raise failed("redraw", e) from e
    try:
        previous = db.sessions.replace_picture(item.id, field, picture_id, scene)
    except KeyError:
        files.remove(picture_id)
        raise HTTPException(status_code=404, detail="the session went away while drawing") from None
    files.remove(previous)
    changes = {field: files.name(picture_id)} | ({"scene": scene.text, "caption": scene.caption or None} if scene else {})
    return item.model_copy(update=changes)


@router.get("/sessions/{session_id}/stars", response_model=Stars)
def get_stars(session_id: int, db: Db) -> Stars:
    require_session(db, session_id)
    return db.sessions.get_stars(session_id)


@router.put("/sessions/{session_id}/stars", response_model=Stars)
def set_stars(session_id: int, body: Stars, db: Db) -> Stars:
    require_session(db, session_id)
    return db.sessions.set_stars(session_id, body)


@router.get("/sessions/{session_id}/note", response_model=Note)
def get_note(session_id: int, db: Db) -> Note:
    require_session(db, session_id)
    return db.sessions.get_note(session_id)


@router.put("/sessions/{session_id}/note", response_model=Note)
def set_note(session_id: int, body: Note, db: Db) -> Note:
    require_session(db, session_id)
    return db.sessions.set_note(session_id, body)
