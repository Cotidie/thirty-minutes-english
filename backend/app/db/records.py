"""What the coaches leave behind: sentences made with a word, paragraphs read aloud
or summed up. Each points at what it practised by id, so it goes when its session goes."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.live.changes import SessionChange
from app.models import Correction, Example, Reading, Summary, SummaryFeedback

if TYPE_CHECKING:
    from app.db import Database


class RecordRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def _announce(self, paragraph_id: int) -> None:
        session_id = self._db.sessions.session_of_paragraph(paragraph_id)
        if session_id is not None:
            self._db.changes.publish(session_id, SessionChange.RECORDS)

    # A sentence made with a word, and the coach's echo.

    def add_example(self, session_id: int, vocabulary_id: int, user_text: str, coach_text: str, seconds: float) -> Example:
        """Raises KeyError unless the word is one of the session's."""
        created_at = datetime.now(UTC)
        with self._db.connect() as conn:
            if conn.execute("SELECT 1 FROM vocabulary WHERE id = ? AND session_id = ?", (vocabulary_id, session_id)).fetchone() is None:
                raise KeyError(vocabulary_id)
            cur = conn.execute(
                "INSERT INTO examples (created_at, vocabulary_id, user_text, coach_text, seconds) VALUES (?, ?, ?, ?, ?)",
                (created_at.isoformat(), vocabulary_id, user_text, coach_text, seconds),
            )
        self._db.changes.publish(session_id, SessionChange.RECORDS)
        return Example(
            id=cur.lastrowid, created_at=created_at, vocabulary_id=vocabulary_id, user_text=user_text, coach_text=coach_text, seconds=seconds
        )

    def list_examples(self, session_id: int) -> list[Example]:
        """In the order they were made, so they stack under each word."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """SELECT x.id, x.created_at, x.vocabulary_id, x.user_text, x.coach_text, x.seconds
                   FROM examples x JOIN vocabulary v ON v.id = x.vocabulary_id
                   WHERE v.session_id = ? ORDER BY x.id""",
                (session_id,),
            ).fetchall()
        return [Example(**dict(row)) for row in rows]

    # One paragraph summed up out loud, and the coach's judgment of it.

    def add_summary(self, paragraph_id: int, user_text: str, feedback: SummaryFeedback, seconds: float) -> Summary:
        created_at = datetime.now(UTC)
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO summaries (created_at, paragraph_id, user_text, feedback, seconds) VALUES (?, ?, ?, ?, ?)",
                (created_at.isoformat(), paragraph_id, user_text, feedback.model_dump_json(), seconds),
            )
        self._announce(paragraph_id)
        return Summary(id=cur.lastrowid, created_at=created_at, paragraph_id=paragraph_id, user_text=user_text, feedback=feedback, seconds=seconds)

    def list_summaries(self, session_id: int) -> list[Summary]:
        """In the order they were made, so they stack under each paragraph."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT s.* FROM summaries s JOIN paragraphs p ON p.id = s.paragraph_id WHERE p.session_id = ? ORDER BY s.id",
                (session_id,),
            ).fetchall()
        return [Summary(**{**dict(row), "feedback": SummaryFeedback.model_validate_json(row["feedback"])}) for row in rows]

    # One paragraph read aloud, and what the assessor stopped the reader on.

    def add_reading(self, paragraph_id: int, user_text: str, seconds: float, corrections: list[Correction]) -> Reading:
        created_at = datetime.now(UTC)
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO readings (created_at, paragraph_id, user_text, seconds, corrections) VALUES (?, ?, ?, ?, ?)",
                (created_at.isoformat(), paragraph_id, user_text, seconds, json.dumps([c.model_dump() for c in corrections])),
            )
        self._announce(paragraph_id)
        return Reading(id=cur.lastrowid, created_at=created_at, paragraph_id=paragraph_id, user_text=user_text, seconds=seconds, corrections=corrections)

    def list_readings(self, session_id: int) -> list[Reading]:
        """Newest first. Readings saved before corrections were kept carry None."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM readings r JOIN paragraphs p ON p.id = r.paragraph_id WHERE p.session_id = ? ORDER BY r.id DESC",
                (session_id,),
            ).fetchall()
        return [
            Reading(**{**dict(row), "corrections": None if row["corrections"] is None else [Correction.model_validate(c) for c in json.loads(row["corrections"])]})
            for row in rows
        ]
