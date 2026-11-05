"""What each Claude call of a session's generation answers, the schemas it answers in, and how the
answers make one `Draft`. The draft brings the research, the edits bring the article's final text,
and the finish brings everything copied from that text."""

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.generation.readability import paragraphs
from app.llm import GenerationError
from app.models import (
    ArticleDraft,
    Draft,
    FigureDraft,
    ParagraphPictureDraft,
    PictureDraft,
    Question,
    SentencePair,
    Source,
    VocabularyDraft,
)

VOCABULARY_COUNT = 8

M = TypeVar("M", bound=BaseModel)
log = logging.getLogger(__name__)


class ArticleText(BaseModel):
    """The article as the editing passes hand it on: a title and a body of paragraphs split by blank lines."""

    title: str
    body: str


class ImageCandidate(BaseModel):
    """An image the drafting pass saw on a page it drew on; the finishing pass places it."""

    image_url: str
    page_url: str
    credit: str = ""
    shows: str


class FirstDraft(ArticleText):
    """The drafting pass's answer: the researched article and what it drew on."""

    sources: list[Source] = []
    images: list[ImageCandidate] = []


class Finish(BaseModel):
    """The finishing pass's answer: everything the session takes from the final article, and its words."""

    topic: str
    questions: list[Question]
    translation: list[SentencePair] = []
    figures: list[FigureDraft] = []
    picture: PictureDraft
    paragraph_picture: ParagraphPictureDraft
    vocabulary: list[VocabularyDraft]


def _strict(required: list[str], properties: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": required, "properties": properties}


_TEXT = {"title": {"type": "string"}, "body": {"type": "string"}}
_STRING = {"type": "string"}

TEXT_SCHEMA: dict = _strict(["title", "body"], _TEXT)

DRAFT_SCHEMA: dict = _strict(
    ["title", "body", "sources", "images"],
    {
        **_TEXT,
        "sources": {
            "type": "array",
            "minItems": 0,
            "maxItems": 5,
            "items": _strict(["title", "url"], {"title": _STRING, "url": _STRING}),
        },
        "images": {
            "type": "array",
            "maxItems": 4,
            "items": _strict(
                ["image_url", "page_url", "credit", "shows"],
                {"image_url": _STRING, "page_url": _STRING, "credit": _STRING, "shows": _STRING},
            ),
        },
    },
)

FINISH_SCHEMA: dict = _strict(
    ["topic", "questions", "translation", "figures", "picture", "paragraph_picture", "vocabulary"],
    {
        "topic": _STRING,
        "questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": _strict(
                ["text", "evidence"],
                {"text": _STRING, "evidence": {"type": "array", "minItems": 0, "maxItems": 2, "items": _STRING}},
            ),
        },
        "translation": {
            "type": "array",
            "minItems": 1,
            "items": _strict(["en", "ko"], {"en": _STRING, "ko": _STRING}),
        },
        "figures": {
            "type": "array",
            "maxItems": 2,
            "items": _strict(
                ["after", "image_url", "page_url", "credit", "caption"],
                {
                    "after": {"type": "integer", "minimum": 0},
                    "image_url": _STRING,
                    "page_url": _STRING,
                    "credit": _STRING,
                    "caption": _STRING,
                },
            ),
        },
        "picture": _strict(["scene", "caption"], {"scene": _STRING, "caption": _STRING}),
        "paragraph_picture": _strict(
            ["after", "scene", "caption"],
            {"after": {"type": "integer", "minimum": 1}, "scene": _STRING, "caption": _STRING},
        ),
        "vocabulary": {
            "type": "array",
            "minItems": VOCABULARY_COUNT,
            "maxItems": VOCABULARY_COUNT,
            "items": _strict(
                ["word", "pos", "definition", "synonyms", "example", "korean", "scene", "caption"],
                {
                    "word": _STRING,
                    "pos": _STRING,
                    "definition": _STRING,
                    "synonyms": {"type": "array", "minItems": 1, "maxItems": 2, "items": _STRING},
                    "example": _STRING,
                    "korean": _STRING,
                    "scene": _STRING,
                    "caption": _STRING,
                },
            ),
        },
    },
)


def parse(model: type[M], payload: dict) -> M:
    """One pass's structured output as its model; a payload that does not fit is a failed generation."""
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        raise GenerationError(f"structured output failed validation: {e}") from e


def assemble(text: ArticleText, first: FirstDraft, finish: Finish) -> Draft:
    """The session as the job stores it: the final text, the draft's sources, and the finish's parts.
    A figure whose image the draft never saw is dropped, since nothing checked that address, and so is
    evidence the article view could not find to mark."""
    seen = {image.image_url for image in first.images}
    return Draft(
        topic=finish.topic,
        article=ArticleDraft(
            title=text.title,
            body=text.body,
            questions=[_with_evidence_in(text.body, question) for question in finish.questions],
            sources=first.sources,
            translation=finish.translation,
            figures=[figure for figure in finish.figures if figure.image_url in seen],
            picture=finish.picture,
            paragraph_picture=finish.paragraph_picture,
        ),
        vocabulary=finish.vocabulary,
    )


def _with_evidence_in(body: str, question: Question) -> Question:
    """The question with only the passages the article view marks: each inside one paragraph, any case, trimmed
    (`markedSpans` in frontend/src/lib/highlight.ts)."""
    parts = [part.lower() for part in paragraphs(body)]
    found = [passage for passage in question.evidence if _marked_in(passage, parts)]
    if dropped := [passage for passage in question.evidence if passage not in found]:
        log.warning("finish: evidence not in the article, dropped: %s", dropped)
    return question.model_copy(update={"evidence": found})


def _marked_in(passage: str, parts: list[str]) -> bool:
    needle = passage.strip().lower()
    return bool(needle) and any(needle in part for part in parts)
