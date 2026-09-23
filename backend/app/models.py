from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Category(StrEnum):
    """Where a suggested topic comes from. Drives the chip colour on the home page."""

    CS = "cs"
    IE = "ie"
    AI = "ai"
    LITERATURE = "literature"
    HISTORY = "history"
    WORLD = "world"
    KOREA = "korea"
    RESEARCH = "research"
    NEWS = "news"


# What each category is called in the key under the chips, in the order the key lists them.
CATEGORY_LABELS: dict[Category, str] = {
    Category.NEWS: "In the news",
    Category.KOREA: "Korea",
    Category.RESEARCH: "Research",
    Category.CS: "Computer science",
    Category.IE: "Industrial engineering",
    Category.AI: "AI",
    Category.LITERATURE: "Literature",
    Category.HISTORY: "History",
    Category.WORLD: "World",
}


class Topic(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    category: Category


class Expression(BaseModel):
    phrase: str
    meaning: str
    """Plainer words for the same meaning; empty on sessions made before they were asked for."""
    synonyms: list[str] = []
    usage_note: str
    examples: list[str]
    """The Korean equivalent, hidden behind a chip until tapped."""
    korean: str | None = None


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

    @model_validator(mode="after")
    def keep_only_sentences_found_in_the_body(self) -> "Article":
        """A pair the reader cannot click on is no use; the sentence stays English."""
        self.translation = [pair for pair in self.translation if pair.en.strip() and pair.en.strip() in self.body]
        return self


class VocabularyItem(BaseModel):
    word: str
    pos: str
    definition: str
    """Plainer words for the same sense; shown with the definition."""
    synonyms: list[str] = []
    example: str
    """The Korean equivalent in the sense used here; hidden on the card until tapped."""
    korean: str | None = None
    """A drawable situation the word fits, written with the session; drawn for the card."""
    scene: str | None = None
    """One or two sentences on what the picture shows and why it is the word; hidden until asked for."""
    caption: str | None = None
    """File name under the images folder, served at /api/images/{image}."""
    image: str | None = None


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
    labels: dict[Category, str] = CATEGORY_LABELS


class ExampleFeedback(BaseModel):
    """The sentence the native way, and a short line per change made, in order of weight."""

    paraphrase: str
    feedback: list[str]


class PhraseCard(BaseModel):
    """One reviewable answer, pulled out of a round's transcripts."""

    asked: str
    english: str
    alternatives: list[str] = []
    note: str = ""


class Correction(BaseModel):
    """One thing the coach stopped the reader on: a word's sound, or a pause inside a phrase."""

    kind: Literal["pronunciation", "phrasing"]
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
