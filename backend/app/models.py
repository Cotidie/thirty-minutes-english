from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class Expression(BaseModel):
    phrase: str
    meaning: str
    usage_note: str
    examples: list[str]


class Question(BaseModel):
    text: str
    evidence: list[str] = []


class Source(BaseModel):
    title: str
    url: str


class Article(BaseModel):
    title: str
    body: str
    questions: list[Question]
    sources: list[Source] = []

    @field_validator("questions", mode="before")
    @classmethod
    def coerce_legacy_strings(cls, value: object) -> object:
        if isinstance(value, list):
            return [{"text": q, "evidence": []} if isinstance(q, str) else q for q in value]
        return value


class VocabularyItem(BaseModel):
    word: str
    pos: str
    definition: str
    example: str


class SessionContent(BaseModel):
    topic: str
    expressions: list[Expression]
    article: Article
    vocabulary: list[VocabularyItem]


class SessionSummary(BaseModel):
    id: int
    created_at: datetime
    topic: str
    title: str


class Session(BaseModel):
    id: int
    created_at: datetime
    topic: str
    content: SessionContent


class CreateSessionRequest(BaseModel):
    topic: str | None = None


class JobStatus(BaseModel):
    id: str
    topic: str
    status: Literal["running", "done", "failed"]
    stage: Literal["starting", "skills", "searching", "writing", "finalizing"]
    searches: int
    elapsed_seconds: float
    stage_elapsed_seconds: float
    expected_seconds: float
    session_id: int | None = None
    error: str | None = None


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class ReadAloudRequest(BaseModel):
    paragraph: str
    sdp: str

    _check = field_validator("paragraph", "sdp")(_not_blank)


class PhraseRequest(BaseModel):
    sdp: str
    topic: str | None = None

    _check = field_validator("sdp")(_not_blank)


class AskRequest(BaseModel):
    session_id: int | None = None
    user_text: str
    coach_text: str
    seconds: float = 0

    _check = field_validator("user_text", "coach_text")(_not_blank)


class PhraseCard(BaseModel):
    """One reviewable answer, pulled out of a round's transcripts."""

    asked: str
    english: str
    alternatives: list[str] = []
    note: str = ""


class Ask(BaseModel):
    id: int
    created_at: datetime
    session_id: int | None
    user_text: str
    coach_text: str
    seconds: float
    card: PhraseCard | None = None


class LiveSession(BaseModel):
    """Passthrough of OpenAI's session-creation answer: {session: {id}, transport: {type, sdp}}."""

    session: dict
    transport: dict
