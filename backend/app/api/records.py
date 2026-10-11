"""What a session leaves behind: sentences made, paragraphs read."""

from fastapi import APIRouter

from app.api.deps import Db, require_session
from app.api.schemas import ExampleRequest, ReadingRequest
from app.models import Example, Reading

router = APIRouter(prefix="/api")


@router.post("/examples", response_model=Example, status_code=201)
def add_example(body: ExampleRequest, db: Db) -> Example:
    require_session(db, body.session_id)
    return db.records.add_example(body.session_id, body.expression, body.user_text, body.coach_text, body.seconds)


@router.get("/examples", response_model=list[Example])
def list_examples(session_id: int, db: Db) -> list[Example]:
    return db.records.list_examples(session_id)


@router.post("/readings", response_model=Reading, status_code=201)
def add_reading(body: ReadingRequest, db: Db) -> Reading:
    require_session(db, body.session_id)
    return db.records.add_reading(
        body.session_id, body.paragraph, body.user_text, body.coach_text, body.seconds, body.corrections
    )


@router.get("/readings", response_model=list[Reading])
def list_readings(db: Db, session_id: int | None = None) -> list[Reading]:
    return db.records.list_readings(session_id)
