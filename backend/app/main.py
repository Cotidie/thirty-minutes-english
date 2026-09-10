import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response

from app.generator import ClaudeCliGenerator, Generator
from app.jobs import Executor, Job, JobRunner
from app.models import CreateSessionRequest, JobStatus, Session, SessionSummary
from app.store import SessionStore
from app.topics import TOPICS, pick_topic

ROOT = Path(__file__).resolve().parent.parent
RECENT_TOPIC_WINDOW = 10


def create_app(store: SessionStore, generator: Generator, executor: Executor | None = None) -> FastAPI:
    app = FastAPI(title="english-speaking-claude")
    app.state.store = store
    app.state.jobs = JobRunner(generator, store, executor)

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

    @app.get("/api/topics", response_model=list[str])
    def list_topics() -> list[str]:
        return list(TOPICS)

    @app.get("/api/sessions", response_model=list[SessionSummary])
    def list_sessions(request: Request) -> list[SessionSummary]:
        return request.app.state.store.list_all()

    @app.post("/api/sessions", response_model=JobStatus, status_code=202)
    def create_session(body: CreateSessionRequest, request: Request) -> JobStatus:
        store: SessionStore = request.app.state.store
        runner: JobRunner = request.app.state.jobs
        topic = body.topic.strip() if body.topic and body.topic.strip() else pick_topic(
            store.recent_topics(RECENT_TOPIC_WINDOW)
        )
        return status_of(runner.start(topic), runner)

    @app.get("/api/jobs/{job_id}", response_model=JobStatus)
    def get_job(job_id: str, request: Request) -> JobStatus:
        runner: JobRunner = request.app.state.jobs
        job = runner.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return status_of(job, runner)

    @app.get("/api/sessions/{session_id}", response_model=Session)
    def get_session(session_id: int, request: Request) -> Session:
        session = request.app.state.store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def delete_session(session_id: int, request: Request) -> Response:
        if not request.app.state.store.delete(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        return Response(status_code=204)

    return app


def default_app() -> FastAPI:
    return create_app(
        SessionStore(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db")),
        ClaudeCliGenerator(
            model=os.environ.get("CLAUDE_MODEL", "opus"),
            effort=os.environ.get("CLAUDE_EFFORT", "xhigh"),
            skills=tuple(s for s in os.environ.get("CLAUDE_SKILLS", "").split(",") if s.strip()),
        ),
    )


app = default_app()
