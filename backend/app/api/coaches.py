"""The voice coaches, the pronunciation assessor, reading aloud, and the text runs behind Practice and Summarize."""

from fastapi import APIRouter, Response

from app.api.deps import Db, Me, Svc, charge, failed, off
from app.api.schemas import (
    AssessorSession,
    ExampleFeedbackRequest,
    ExampleSessionRequest,
    LiveSession,
    ParagraphRequest,
    SpeechRequest,
    SummaryFeedbackRequest,
)
from app.llm import GenerationError
from app.models import ExampleFeedback, SummaryFeedback
from app.net import HttpError
from app.voice.live import LiveAgent
from app.wiring import Services

router = APIRouter(prefix="/api")


def live_agent(services: Services, name: str) -> LiveAgent:
    agent = services.agents.get(name)
    if agent is None:
        raise off(f"{name} is off: set GEMINI_API_KEY in Settings")
    return agent


def start_live(agent: LiveAgent, **values: str) -> dict:
    try:
        return agent.start(**values)
    except HttpError as e:
        raise failed("voice session", e) from e


@router.post("/read-aloud/sessions", response_model=LiveSession, status_code=201)
def start_read_aloud(body: ParagraphRequest, db: Db, me: Me, services: Svc) -> dict:
    agent = live_agent(services, "read-aloud")
    charge(db, me, "read_aloud_voice")
    return start_live(agent, paragraph=body.paragraph)


@router.post("/summary/sessions", response_model=LiveSession, status_code=201)
def start_summary(body: ParagraphRequest, db: Db, me: Me, services: Svc) -> dict:
    """A round that only writes down what the reader says the paragraph is about, primed with its words."""
    transcriber = services.transcriber
    if transcriber is None:
        raise off("Summarize is off: set GEMINI_API_KEY in Settings")
    charge(db, me, "summary_voice")
    try:
        return transcriber.start(body.paragraph)
    except HttpError as e:
        raise failed("transcription session", e) from e


@router.post("/summary/feedback", response_model=SummaryFeedback)
def summary_feedback(body: SummaryFeedbackRequest, db: Db, me: Me, services: Svc) -> SummaryFeedback:
    coach = services.summary_coach
    if coach is None:
        raise off("summary coach is off: the summary-coach folder is missing")
    charge(db, me, "summary_feedback")
    try:
        return coach.feedback(body.paragraph, body.user_text)
    except GenerationError as e:
        raise failed("feedback", e) from e


@router.post("/example/sessions", response_model=LiveSession, status_code=201)
def start_example(body: ExampleSessionRequest, db: Db, me: Me, services: Svc) -> dict:
    agent = live_agent(services, "example")
    charge(db, me, "practice_voice", body.word)
    return start_live(agent, word=body.word, meaning=body.meaning, pos=body.pos)


@router.get("/assessor/token", response_model=AssessorSession)
def assessor_token(db: Db, me: Me, services: Svc) -> dict:
    if services.assessor is None:
        raise off("Read aloud is off: set AZURE_SPEECH_KEY in Settings")
    charge(db, me, "read_aloud_token")
    try:
        return services.assessor.session()
    except HttpError as e:
        raise failed("assessor token", e) from e


@router.post("/example/feedback", response_model=ExampleFeedback)
def example_feedback(body: ExampleFeedbackRequest, db: Db, me: Me, services: Svc) -> ExampleFeedback:
    coach = services.example_coach
    if coach is None:
        raise off("example coach is off: the example-coach folder is missing")
    charge(db, me, "practice_feedback", body.word)
    try:
        return coach.feedback(body.word, body.pos, body.meaning, body.user_text, body.scene)
    except GenerationError as e:
        raise failed("feedback", e) from e


@router.post("/speech", response_class=Response)
def speech(body: SpeechRequest, db: Db, me: Me, services: Svc) -> Response:
    """The sentence read aloud in the coaches' voice; a sentence read before comes from disk, free."""
    if services.speaker is None:
        raise off("reading aloud is off: set GEMINI_API_KEY in Settings")
    if not services.speaker.cached(body.text):
        charge(db, me, "speech", " ".join(body.text.split())[:40])
    try:
        audio = services.speaker.read(body.text)
    except GenerationError as e:
        raise failed("reading aloud", e) from e
    return Response(audio, media_type=services.speaker.media_type, headers={"Cache-Control": "private, max-age=86400"})
