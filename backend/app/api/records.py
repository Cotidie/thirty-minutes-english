"""What a session leaves behind: sentences made, paragraphs read and summed up."""

from fastapi import APIRouter, HTTPException

from app.api.deps import Db, require_paragraph, require_session
from app.api.schemas import ExampleRequest, ReadingRequest, SummaryRequest
from app.models import Example, Reading, Summary

router = APIRouter(prefix="/api")


@router.post("/examples", response_model=Example, status_code=201)
def add_example(body: ExampleRequest, db: Db) -> Example:
    require_session(db, body.session_id)
    try:
        return db.records.add_example(body.session_id, body.vocabulary_id, body.user_text, body.coach_text, body.seconds)
    except KeyError:
        raise HTTPException(status_code=404, detail="not a word of this session") from None


@router.get("/examples", response_model=list[Example])
def list_examples(session_id: int, db: Db) -> list[Example]:
    return db.records.list_examples(session_id)


@router.post("/summaries", response_model=Summary, status_code=201)
def add_summary(body: SummaryRequest, db: Db) -> Summary:
    require_paragraph(db, body.paragraph_id)
    return db.records.add_summary(body.paragraph_id, body.user_text, body.feedback, body.seconds)


@router.get("/summaries", response_model=list[Summary])
def list_summaries(session_id: int, db: Db) -> list[Summary]:
    return db.records.list_summaries(session_id)


@router.post("/readings", response_model=Reading, status_code=201)
def add_reading(body: ReadingRequest, db: Db) -> Reading:
    require_paragraph(db, body.paragraph_id)
    return db.records.add_reading(body.paragraph_id, body.user_text, body.seconds, body.corrections)


@router.get("/readings", response_model=list[Reading])
def list_readings(session_id: int, db: Db) -> list[Reading]:
    return db.records.list_readings(session_id)
