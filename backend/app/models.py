from datetime import datetime

from pydantic import BaseModel


class Expression(BaseModel):
    phrase: str
    meaning: str
    usage_note: str
    examples: list[str]


class Article(BaseModel):
    title: str
    body: str
    questions: list[str]


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
