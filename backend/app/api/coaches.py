"""The voice coaches, the pronunciation assessor, reading aloud, and the text runs behind Practice and Summarize."""

from fastapi import APIRouter, Depends, Response

from app.api.deps import Svc, can_practice, failed, off
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
from app.wiring import Services

router = APIRouter(prefix="/api", dependencies=[Depends(can_practice)])


def start_live(services: Services, name: str, **values: str) -> dict:
    agent = services.agents.get(name)
    if agent is None:
        raise off(f"{name} is off: set GEMINI_API_KEY in Settings")
    try:
        return agent.start(**values)
    except HttpError as e:
        raise failed("voice session", e) from e


@router.post("/read-aloud/sessions", response_model=LiveSession, status_code=201)
def start_read_aloud(body: ParagraphRequest, services: Svc) -> dict:
    return start_live(services, "read-aloud", paragraph=body.paragraph)


@router.post("/summary/sessions", response_model=LiveSession, status_code=201)
def start_summary(body: ParagraphRequest, services: Svc) -> dict:
    """A round that only writes down what the reader says the paragraph is about, primed with its words."""
    transcriber = services.transcriber
    if transcriber is None:
        raise off("Summarize is off: set GEMINI_API_KEY in Settings")
    try:
        return transcriber.start(body.paragraph)
    except HttpError as e:
        raise failed("transcription session", e) from e


@router.post("/summary/feedback", response_model=SummaryFeedback)
def summary_feedback(body: SummaryFeedbackRequest, services: Svc) -> SummaryFeedback:
    coach = services.summary_coach
    if coach is None:
        raise off("summary coach is off: the summary-coach folder is missing")
    try:
        return coach.feedback(body.paragraph, body.user_text)
    except GenerationError as e:
        raise failed("feedback", e) from e


@router.post("/example/sessions", response_model=LiveSession, status_code=201)
def start_example(body: ExampleSessionRequest, services: Svc) -> dict:
    return start_live(services, "example", word=body.word, meaning=body.meaning, pos=body.pos)


@router.get("/assessor/token", response_model=AssessorSession)
def assessor_token(services: Svc) -> dict:
    if services.assessor is None:
        raise off("Read aloud is off: set AZURE_SPEECH_KEY in Settings")
    try:
        return services.assessor.session()
    except HttpError as e:
        raise failed("assessor token", e) from e


@router.post("/example/feedback", response_model=ExampleFeedback)
def example_feedback(body: ExampleFeedbackRequest, services: Svc) -> ExampleFeedback:
    coach = services.example_coach
    if coach is None:
        raise off("example coach is off: the example-coach folder is missing")
    try:
        return coach.feedback(body.word, body.pos, body.meaning, body.user_text, body.scene)
    except GenerationError as e:
        raise failed("feedback", e) from e


@router.post("/speech", response_class=Response)
def speech(body: SpeechRequest, services: Svc) -> Response:
    """The sentence read aloud in the coaches' voice; a sentence read before comes from disk."""
    if services.speaker is None:
        raise off("reading aloud is off: set GEMINI_API_KEY in Settings")
    try:
        audio = services.speaker.read(body.text)
    except GenerationError as e:
        raise failed("reading aloud", e) from e
    return Response(audio, media_type=services.speaker.media_type, headers={"Cache-Control": "private, max-age=86400"})
