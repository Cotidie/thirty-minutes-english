"""What a session leaves behind: sentences made, paragraphs read and summed up."""

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import Db, Judges, Me, Svc, held_or_402, off, require_access, require_paragraph
from app.coaching.summary_feedback import SummaryCoach
from app.db import Database
from app.api.schemas import ExampleRequest, ReadingRequest, SummaryRequest
from app.models import Example, Reading, Summary, User

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
def add_summary(body: SummaryRequest, db: Db, me: Me, services: Svc, judges: Judges) -> Summary:
    """Keeps what was said and answers at once; the feedback follows in the background, announced as `records`."""
    require_paragraph(db, me, body.paragraph_id)
    coach = summary_coach(services.summary_coach)
    hold = held_or_402(db, me, "summary_feedback")
    try:
        summary_id = db.records.start_summary(body.paragraph_id, me.id, body.user_text, body.seconds)
    except BaseException:
        db.credits.release(hold)
        raise
    judges.judge(summary_id, coach, hold)
    return summary_as_seen(db, summary_id, me.id)


@router.post("/summaries/{summary_id}/judge", response_model=Summary)
def judge_summary_again(summary_id: int, db: Db, me: Me, services: Svc, judges: Judges) -> Summary:
    """A summary whose feedback failed, judged again with what was said; whoever asks pays."""
    summary = summary_in_reach(db, summary_id, me)
    coach = summary_coach(services.summary_coach)
    hold = held_or_402(db, me, "summary_feedback")
    if not db.records.rejudge_summary(summary.id):
        db.credits.release(hold)
        raise HTTPException(status_code=409, detail="Only a summary whose feedback failed can be judged again.")
    judges.judge(summary.id, coach, hold)
    return summary_as_seen(db, summary.id, me.id)


@router.delete("/summaries/{summary_id}", status_code=204)
def remove_summary(summary_id: int, db: Db, me: Me) -> Response:
    summary = summary_in_reach(db, summary_id, me)
    if not db.records.remove_failed_summary(summary.id):
        raise HTTPException(status_code=409, detail="Only a summary whose feedback failed can be removed.")
    return Response(status_code=204)


@router.get("/summaries", response_model=list[Summary])
def list_summaries(session_id: int, db: Db, me: Me) -> list[Summary]:
    require_access(db, me, session_id)
    return db.records.list_summaries(session_id, me.id)


@router.post("/readings", response_model=Reading, status_code=201)
def add_reading(body: ReadingRequest, db: Db, me: Me) -> Reading:
    require_paragraph(db, me, body.paragraph_id)
    return db.records.add_reading(body.paragraph_id, body.user_text, body.seconds, body.corrections)


@router.get("/readings", response_model=list[Reading])
def list_readings(session_id: int, db: Db, me: Me) -> list[Reading]:
    require_access(db, me, session_id)
    return db.records.list_readings(session_id)


def summary_coach(coach: SummaryCoach | None) -> SummaryCoach:
    if coach is None:
        raise off("summary coach is off: the summary-coach folder is missing")
    return coach


def summary_in_reach(db: Database, summary_id: int, me: User) -> Summary:
    """404 unless the summary is of a session `me` may open; the same 404 either way."""
    summary = db.records.get_summary(summary_id, me.id)
    if summary is None or not db.shares.can_access(me, db.sessions.session_of_paragraph(summary.paragraph_id)):
        raise HTTPException(status_code=404, detail="summary not found")
    return summary


def summary_as_seen(db: Database, summary_id: int, me_id: int) -> Summary:
    """Where the judgment ran on the spot, the session may have gone with it."""
    summary = db.records.get_summary(summary_id, me_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="paragraph not found")
    return summary
