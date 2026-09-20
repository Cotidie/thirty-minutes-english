import logging
import os
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response

from app.assessor import AssessorError
from app.cards import AskReview
from app.claude_cli import GenerationError
from app.daily_topics import DailyTopics
from app.jobs import Executor, Job, JobRunner
from app.keycheck import check_key
from app.live import LiveAgent, LiveSessionError
from app.models import (
    Ask,
    AskRequest,
    AssessorSession,
    TopicListing,
    Reading,
    ReadingRequest,
    CreateSessionRequest,
    Example,
    ExampleFeedback,
    ExampleFeedbackRequest,
    ExampleRequest,
    ExampleSessionRequest,
    JobStatus,
    KeyTestRequest,
    KeyTestResult,
    LiveSession,
    PhraseRequest,
    Phrasing,
    PhrasingRequest,
    ReadAloudRequest,
    Session,
    SessionSummary,
    SettingField,
    SettingsUpdate,
    SettingsView,
    Stars,
)
from app.settings import InvalidSetting, Settings, SettingsStore
from app.store import SessionStore
from app.topics import pick_topic
from app.wiring import Services, build_services

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIRS = {
    "read-aloud": ("READ_ALOUD_AGENT_DIR", ROOT.parent.parent / "read-aloud-coach"),
    "phrase": ("PHRASE_AGENT_DIR", ROOT.parent.parent / "phrase-coach"),
    "example": ("EXAMPLE_AGENT_DIR", ROOT.parent.parent / "example-coach"),
}
RECENT_TOPIC_WINDOW = 10


Rebuild = Callable[[Settings], Services]


def create_app(
    store: SessionStore,
    services: Services,
    executor: Executor | None = None,
    settings_store: SettingsStore | None = None,
    rebuild: Rebuild | None = None,
    env: dict[str, str] | None = None,
) -> FastAPI:
    """`rebuild` turns saved settings into fresh services; without it a settings
    change is stored but the running services stay as they are (tests)."""
    app = FastAPI(title="english-speaking-claude")
    app.state.store = store
    app.state.settings_store = settings_store or SettingsStore(store.path)
    app.state.env = os.environ if env is None else env
    app.state.rebuild = rebuild
    app.state.jobs = JobRunner(services.generator, store, executor)
    app.state.topics = DailyTopics(store, services.topic_source, app.state.jobs.executor)
    app.state.asks = AskReview(store, services.extractor)
    app.state.services = services

    def current_settings(request: Request) -> Settings:
        return Settings.resolve(request.app.state.env, request.app.state.settings_store)

    def apply_services(request: Request, services: Services) -> None:
        state = request.app.state
        state.services = services
        state.jobs.generator = services.generator
        state.topics.source = services.topic_source
        state.asks.extractor = services.extractor

    def live_agent(request: Request, name: str) -> LiveAgent:
        services: Services = request.app.state.services
        agent = services.agents.get(name)
        if agent is None:
            raise HTTPException(
                status_code=503, detail=f"{name} is off: set {services.voice_key_name} in Settings"
            )
        return agent

    def start_live(agent: LiveAgent, sdp: str | None, **values: str) -> dict:
        try:
            return agent.start(sdp, **values)
        except LiveSessionError as e:
            raise HTTPException(status_code=502, detail=f"voice session failed: {e.message}") from e

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

    @app.get("/api/settings", response_model=SettingsView)
    def get_settings(request: Request) -> SettingsView:
        return SettingsView(fields=[SettingField(**vars(f)) for f in current_settings(request).fields()])

    @app.put("/api/settings", response_model=SettingsView)
    def put_settings(body: SettingsUpdate, request: Request) -> SettingsView:
        try:
            request.app.state.settings_store.save(body.values)
        except InvalidSetting as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        settings = current_settings(request)
        rebuild: Rebuild | None = request.app.state.rebuild
        if rebuild is not None:
            apply_services(request, rebuild(settings))
        return SettingsView(fields=[SettingField(**vars(f)) for f in settings.fields()])

    @app.post("/api/settings/test-key", response_model=KeyTestResult)
    def test_key(body: KeyTestRequest, request: Request) -> KeyTestResult:
        settings = current_settings(request)
        key = body.value.strip() or settings.get(body.key)
        result = check_key(body.key, key, region=settings.azure_speech_region)
        return KeyTestResult(ok=result.ok, message=result.message)

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

    @app.get("/api/assessor/token", response_model=AssessorSession)
    def assessor_token(request: Request) -> dict:
        assessor = request.app.state.services.assessor
        if assessor is None:
            raise HTTPException(status_code=503, detail="Read aloud is off: set AZURE_SPEECH_KEY in Settings")
        try:
            return assessor.session()
        except AssessorError as e:
            raise HTTPException(status_code=502, detail=f"assessor token failed: {e.message}") from e

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

    @app.post("/api/example/feedback", response_model=ExampleFeedback)
    def example_feedback(body: ExampleFeedbackRequest, request: Request) -> ExampleFeedback:
        coach = request.app.state.services.example_coach
        if coach is None:
            raise HTTPException(status_code=503, detail="example coach is off: the example-coach folder is missing")
        try:
            return coach.feedback(body.expression, body.meaning, body.usage_note, body.user_text)
        except GenerationError as e:
            raise HTTPException(status_code=502, detail=f"feedback failed: {e}") from e

    @app.post("/api/phrasing", response_model=Phrasing)
    def phrasing(body: PhrasingRequest, request: Request) -> Phrasing:
        """Where a fluent reader pauses in the paragraph; marked once, cached after."""
        store: SessionStore = request.app.state.store
        cached = store.get_phrasing(body.paragraph)
        if cached is not None:
            return Phrasing(breaks=cached)
        marker = request.app.state.services.phrasing
        if marker is None:
            raise HTTPException(status_code=503, detail="phrasing is off: the read-aloud-coach folder has no phrasing prompt")
        try:
            breaks = marker.mark(body.paragraph)
        except GenerationError as e:
            raise HTTPException(status_code=502, detail=f"phrasing failed: {e}") from e
        store.set_phrasing(body.paragraph, breaks)
        return Phrasing(breaks=breaks)

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
        return store.add_reading(
            body.session_id, body.paragraph, body.user_text, body.coach_text, body.seconds, body.corrections
        )

    @app.get("/api/readings", response_model=list[Reading])
    def list_readings(request: Request, session_id: int | None = None) -> list[Reading]:
        return request.app.state.store.list_readings(session_id)

    return app


def agent_dirs() -> dict[str, Path]:
    return {name: Path(os.environ.get(env_var, default)) for name, (env_var, default) in AGENT_DIRS.items()}


def default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = SessionStore(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db"))
    settings_store = SettingsStore(store.path)
    dirs = agent_dirs()
    return create_app(
        store,
        build_services(Settings.resolve(os.environ, settings_store), dirs),
        settings_store=settings_store,
        rebuild=lambda settings: build_services(settings, dirs),
    )


app = default_app()
