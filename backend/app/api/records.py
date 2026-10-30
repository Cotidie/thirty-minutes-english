"""What a session leaves behind: sentences made, paragraphs read and summed up."""

from fastapi import APIRouter, HTTPException

from app.api.deps import Db, Me, require_access, require_paragraph
from app.api.schemas import ExampleRequest, ReadingRequest, SummaryRequest
from app.models import Example, Reading, Summary

router = APIRouter(prefix="/api")


@router.post("/examples", response_model=Example, status_code=201)
def add_example(body: ExampleRequest, db: Db, me: Me) -> Example:
    require_access(db, me, body.session_id)
    try:
        return db.records.add_example(body.session_id, body.vocabulary_id, body.user_text, body.coach_text, body.seconds)
    except KeyError:
        raise HTTPException(status_code=404, detail="not a word of this session") from None


@router.get("/examples", response_model=list[Example])
def list_examples(session_id: int, db: Db, me: Me) -> list[Example]:
    require_access(db, me, session_id)
    return db.records.list_examples(session_id)


@router.post("/summaries", response_model=Summary, status_code=201)
def add_summary(body: SummaryRequest, db: Db, me: Me) -> Summary:
    require_paragraph(db, me, body.paragraph_id)
    return db.records.add_summary(body.paragraph_id, body.user_text, body.feedback, body.seconds)


@router.get("/summaries", response_model=list[Summary])
def list_summaries(session_id: int, db: Db, me: Me) -> list[Summary]:
    require_access(db, me, session_id)
    return db.records.list_summaries(session_id)


@router.post("/readings", response_model=Reading, status_code=201)
def add_reading(body: ReadingRequest, db: Db, me: Me) -> Reading:
    require_paragraph(db, me, body.paragraph_id)
    return db.records.add_reading(body.paragraph_id, body.user_text, body.seconds, body.corrections)


@router.get("/readings", response_model=list[Reading])
def list_readings(session_id: int, db: Db, me: Me) -> list[Reading]:
    require_access(db, me, session_id)
    return db.records.list_readings(session_id)
