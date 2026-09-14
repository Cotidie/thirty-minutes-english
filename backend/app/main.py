import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response

from app.generator import ClaudeCliGenerator, Generator
from app.jobs import Executor, Job, JobRunner
from app.live import AgentDefinition, LiveAgent, LiveSessionError, OpenAILiveSessions
from app.models import (
    Ask,
    AskRequest,
    CreateSessionRequest,
    JobStatus,
    LiveSession,
    PhraseRequest,
    ReadAloudRequest,
    Session,
    SessionSummary,
)
from app.store import SessionStore
from app.topics import TOPICS, pick_topic

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIRS = {
    "read-aloud": ("READ_ALOUD_AGENT_DIR", ROOT.parent.parent / "read-aloud-coach"),
    "phrase": ("PHRASE_AGENT_DIR", ROOT.parent.parent / "phrase-coach"),
}
RECENT_TOPIC_WINDOW = 10


def create_app(
    store: SessionStore,
    generator: Generator,
    executor: Executor | None = None,
    agents: dict[str, LiveAgent] | None = None,
) -> FastAPI:
    app = FastAPI(title="english-speaking-claude")
    app.state.store = store
    app.state.jobs = JobRunner(generator, store, executor)
    app.state.agents = agents or {}

    def live_agent(request: Request, name: str) -> LiveAgent:
        agent = request.app.state.agents.get(name)
        if agent is None:
            raise HTTPException(status_code=503, detail=f"{name} is off: set OPENAI_API_KEY on the backend")
        return agent

    def start_live(agent: LiveAgent, sdp: str, **values: str) -> dict:
        try:
            return agent.start(sdp, **values)
        except LiveSessionError as e:
            raise HTTPException(status_code=502, detail=f"GPT-Live session failed: {e.message}") from e

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

    @app.post("/api/read-aloud/sessions", response_model=LiveSession, status_code=201)
    def start_read_aloud(body: ReadAloudRequest, request: Request) -> dict:
        return start_live(live_agent(request, "read-aloud"), body.sdp, paragraph=body.paragraph)

    @app.post("/api/phrase/sessions", response_model=LiveSession, status_code=201)
    def start_phrase(body: PhraseRequest, request: Request) -> dict:
        return start_live(live_agent(request, "phrase"), body.sdp, topic=body.topic or "an English conversation")

    @app.post("/api/asks", response_model=Ask, status_code=201)
    def add_ask(body: AskRequest, request: Request) -> Ask:
        store: SessionStore = request.app.state.store
        if body.session_id is not None and store.get(body.session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return store.add_ask(body.session_id, body.user_text, body.coach_text, body.seconds)

    @app.get("/api/asks", response_model=list[Ask])
    def list_asks(request: Request, session_id: int | None = None) -> list[Ask]:
        return request.app.state.store.list_asks(session_id)

    return app


def live_agents() -> dict[str, LiveAgent]:
    """Every agent whose folder is present, once an API key is configured."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}
    sessions = OpenAILiveSessions(api_key)
    agents = {}
    for name, (env_var, default) in AGENT_DIRS.items():
        agent_dir = Path(os.environ.get(env_var, default))
        if (agent_dir / "session.json").is_file():
            agents[name] = LiveAgent(name, AgentDefinition(agent_dir), sessions)
        else:
            logging.getLogger(__name__).warning("%s agent folder not found: %s", name, agent_dir)
    return agents


def default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return create_app(
        SessionStore(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db")),
        ClaudeCliGenerator(
            model=os.environ.get("CLAUDE_MODEL", "opus"),
            effort=os.environ.get("CLAUDE_EFFORT", "xhigh"),
            skills=tuple(s for s in os.environ.get("CLAUDE_SKILLS", "").split(",") if s.strip()),
        ),
        agents=live_agents(),
    )


app = default_app()
