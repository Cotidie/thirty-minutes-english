from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Category(StrEnum):
    """Where a suggested topic comes from. Drives the chip colour on the home page."""

    TECH = "tech"
    LITERATURE = "literature"
    HISTORY = "history"
    WORLD = "world"
    NEWS = "news"


class Topic(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    category: Category


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


class SentencePair(BaseModel):
    """One sentence of the body, copied exactly, and its Korean."""

    en: str
    ko: str


class Article(BaseModel):
    title: str
    body: str
    questions: list[Question]
    sources: list[Source] = []
    translation: list[SentencePair] = []

    @field_validator("questions", mode="before")
    @classmethod
    def coerce_legacy_strings(cls, value: object) -> object:
        if isinstance(value, list):
            return [{"text": q, "evidence": []} if isinstance(q, str) else q for q in value]
        return value

    @model_validator(mode="after")
    def keep_only_sentences_found_in_the_body(self) -> "Article":
        """A pair the reader cannot click on is no use; the sentence stays English."""
        self.translation = [pair for pair in self.translation if pair.en.strip() and pair.en.strip() in self.body]
        return self


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


class Stars(BaseModel):
    """What the pair starred in a session, by phrase and by word."""

    expressions: list[str] = []
    words: list[str] = []


class TopicListing(BaseModel):
    """The day's suggestions, whether the news half is still on its way, and why the last fetch failed."""

    topics: list[Topic]
    pending: bool
    error: str | None = None


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


class ExampleSessionRequest(BaseModel):
    sdp: str
    expression: str
    meaning: str
    usage_note: str = ""

    _check = field_validator("sdp", "expression", "meaning")(_not_blank)


class ExampleFeedbackRequest(BaseModel):
    """One sentence a reader made with a target, for the coach to say back and judge."""

    expression: str
    meaning: str
    usage_note: str = ""
    user_text: str

    _check = field_validator("expression", "meaning", "user_text")(_not_blank)


class ExampleFeedback(BaseModel):
    """The sentence the native way, and a short line per change made, in order of weight."""

    paraphrase: str
    feedback: list[str]


class ExampleRequest(BaseModel):
    session_id: int
    expression: str
    user_text: str
    coach_text: str
    seconds: float = 0

    _check = field_validator("expression", "user_text", "coach_text")(_not_blank)


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


class ReadingRequest(BaseModel):
    session_id: int | None = None
    paragraph: str
    user_text: str
    coach_text: str
    seconds: float = 0

    _check = field_validator("paragraph", "coach_text")(_not_blank)


class Correction(BaseModel):
    """One thing the coach stopped the reader on: a word's sound, or a pause inside a phrase."""

    kind: Literal["pronunciation", "phrasing"] = "pronunciation"  # rounds saved before phrasing had none
    word: str
    heard: str
    fix: str
    repeated_ok: bool = False


class Reading(BaseModel):
    id: int
    created_at: datetime
    session_id: int | None
    paragraph: str
    user_text: str
    coach_text: str
    seconds: float
    corrections: list[Correction] | None = None


class Example(BaseModel):
    """One sentence a reader made with an expression, and the coach's echo of it."""

    id: int
    created_at: datetime
    session_id: int
    expression: str
    user_text: str
    coach_text: str
    seconds: float


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
