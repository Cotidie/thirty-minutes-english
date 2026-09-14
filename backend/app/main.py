import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response

from app.cards import AskReview, CorrectionExtractor, Extractor, PhraseCardExtractor, ReadingReview
from app.daily_topics import ClaudeTopicSource, DailyTopics, TopicSource
from app.generator import ClaudeCliGenerator, Generator
from app.jobs import Executor, Job, JobRunner
from app.live import AgentDefinition, LiveAgent, LiveSessionError, OpenAILiveSessions
from app.models import (
    Ask,
    AskRequest,
    TopicListing,
    Reading,
    ReadingRequest,
    CreateSessionRequest,
    Example,
    ExampleRequest,
    ExampleSessionRequest,
    JobStatus,
    LiveSession,
    PhraseRequest,
    ReadAloudRequest,
    Session,
    SessionSummary,
    Stars,
)
from app.store import SessionStore
from app.topics import TOPICS, pick_topic

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIRS = {
    "read-aloud": ("READ_ALOUD_AGENT_DIR", ROOT.parent.parent / "read-aloud-coach"),
    "phrase": ("PHRASE_AGENT_DIR", ROOT.parent.parent / "phrase-coach"),
    "example": ("EXAMPLE_AGENT_DIR", ROOT.parent.parent / "example-coach"),
}
RECENT_TOPIC_WINDOW = 10


def create_app(
    store: SessionStore,
    generator: Generator,
    executor: Executor | None = None,
    agents: dict[str, LiveAgent] | None = None,
    extractor: Extractor | None = None,
    corrections: Extractor | None = None,
    topic_source: TopicSource | None = None,
) -> FastAPI:
    app = FastAPI(title="english-speaking-claude")
    app.state.store = store
    app.state.jobs = JobRunner(generator, store, executor)
    app.state.topics = DailyTopics(store, topic_source, app.state.jobs.executor)
    app.state.agents = agents or {}
    app.state.asks = AskReview(store, extractor)
    app.state.readings = ReadingReview(store, corrections)

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

    @app.get("/api/topics", response_model=TopicListing)
    def list_topics(request: Request) -> TopicListing:
        daily: DailyTopics = request.app.state.topics
        daily.ensure_fetched()
        return daily.listing()

    @app.get("/api/sessions", response_model=list[SessionSummary])
    def list_sessions(request: Request) -> list[SessionSummary]:
        return request.app.state.store.list_all()

    @app.post("/api/topics/refresh", response_model=TopicListing)
    def refresh_topics(request: Request) -> TopicListing:
        daily: DailyTopics = request.app.state.topics
        daily.refresh()
        return daily.listing()

    @app.post("/api/sessions", response_model=JobStatus, status_code=202)
    def create_session(body: CreateSessionRequest, request: Request) -> JobStatus:
        store: SessionStore = request.app.state.store
        runner: JobRunner = request.app.state.jobs
        topic = body.topic.strip() if body.topic and body.topic.strip() else pick_topic(
            store.recent_topics(RECENT_TOPIC_WINDOW)
        )
        return status_of(runner.start(topic), runner)

    @app.get("/api/jobs", response_model=list[JobStatus])
    def list_running_jobs(request: Request) -> list[JobStatus]:
        runner: JobRunner = request.app.state.jobs
        return [status_of(job, runner) for job in runner.running()]

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

    @app.get("/api/sessions/{session_id}/stars", response_model=Stars)
    def get_stars(session_id: int, request: Request) -> Stars:
        store: SessionStore = request.app.state.store
        if store.get(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return store.get_stars(session_id)

    @app.put("/api/sessions/{session_id}/stars", response_model=Stars)
    def set_stars(session_id: int, body: Stars, request: Request) -> Stars:
        store: SessionStore = request.app.state.store
        if store.get(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return store.set_stars(session_id, body)

    @app.post("/api/read-aloud/sessions", response_model=LiveSession, status_code=201)
    def start_read_aloud(body: ReadAloudRequest, request: Request) -> dict:
        return start_live(live_agent(request, "read-aloud"), body.sdp, paragraph=body.paragraph)

    @app.post("/api/phrase/sessions", response_model=LiveSession, status_code=201)
    def start_phrase(body: PhraseRequest, request: Request) -> dict:
        return start_live(live_agent(request, "phrase"), body.sdp, topic=body.topic or "an English conversation")

    @app.post("/api/example/sessions", response_model=LiveSession, status_code=201)
    def start_example(body: ExampleSessionRequest, request: Request) -> dict:
        return start_live(
            live_agent(request, "example"),
            body.sdp,
            expression=body.expression,
            meaning=body.meaning,
            usage_note=body.usage_note or "none",
        )

    @app.post("/api/examples", response_model=Example, status_code=201)
    def add_example(body: ExampleRequest, request: Request) -> Example:
        store: SessionStore = request.app.state.store
        if store.get(body.session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return store.add_example(body.session_id, body.expression, body.user_text, body.coach_text, body.seconds)

    @app.get("/api/examples", response_model=list[Example])
    def list_examples(session_id: int, request: Request) -> list[Example]:
        return request.app.state.store.list_examples(session_id)

    @app.post("/api/asks", response_model=Ask, status_code=201)
    def add_ask(body: AskRequest, request: Request) -> Ask:
        store: SessionStore = request.app.state.store
        if body.session_id is not None and store.get(body.session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return store.add_ask(body.session_id, body.user_text, body.coach_text, body.seconds)

    @app.get("/api/asks", response_model=list[Ask])
    def list_asks(request: Request, session_id: int | None = None) -> list[Ask]:
        return request.app.state.store.list_asks(session_id)

    @app.post("/api/asks/cards", response_model=list[Ask])
    def ask_cards(request: Request, session_id: int | None = None) -> list[Ask]:
        return request.app.state.asks.cards_for(session_id)

    @app.post("/api/readings", response_model=Reading, status_code=201)
    def add_reading(body: ReadingRequest, request: Request) -> Reading:
        store: SessionStore = request.app.state.store
        if body.session_id is not None and store.get(body.session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return store.add_reading(body.session_id, body.paragraph, body.user_text, body.coach_text, body.seconds)

    @app.post("/api/readings/corrections", response_model=list[Reading])
    def reading_corrections(request: Request, session_id: int | None = None) -> list[Reading]:
        return request.app.state.readings.corrections_for(session_id)

    return app


def _extractor(agent: str, schema: str, build) -> Extractor | None:
    """An extractor per agent folder, once a key and that folder's schema exist."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    agent_dir = Path(os.environ.get(*AGENT_DIRS[agent]))
    if not api_key or not (agent_dir / schema).is_file():
        return None
    return build(api_key, agent_dir, os.environ.get("SUMMARY_MODEL", "gpt-5.6-luna"))


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
        topic_source=ClaudeTopicSource(
            model=os.environ.get("TOPICS_MODEL", "sonnet"),
            effort=os.environ.get("TOPICS_EFFORT", "medium"),
        ),
        extractor=_extractor("phrase", "cards.schema.json", PhraseCardExtractor),
        corrections=_extractor("read-aloud", "feedback.schema.json", CorrectionExtractor),
    )


app = default_app()
