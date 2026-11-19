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

    # One paragraph summed up out loud, kept at once and judged in the background: `judging` until the feedback is in
    # (`done`) or could not be had (`failed`). Each step changes a summary only from the state it expects, so two
    # people acting on one summary at once cannot both move it.

    def start_summary(self, paragraph_id: int, user_id: int | None, user_text: str, seconds: float) -> int:
        """Keeps what `user_id` said, waiting for its feedback."""
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO summaries (created_at, paragraph_id, user_id, user_text, status, seconds) VALUES (?, ?, ?, ?, 'judging', ?)",
                (datetime.now(UTC).isoformat(), paragraph_id, user_id, user_text, seconds),
            )
        self._announce(paragraph_id)
        return cur.lastrowid

    def summary_to_judge(self, summary_id: int) -> tuple[str, str] | None:
        """The paragraph and what was said of it, for a summary waiting for its feedback; None for any other."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT p.text, s.user_text FROM summaries s JOIN paragraphs p ON p.id = s.paragraph_id WHERE s.id = ? AND s.status = 'judging'",
                (summary_id,),
            ).fetchone()
        return (row["text"], row["user_text"]) if row else None

    def finish_summary(self, summary_id: int, feedback: SummaryFeedback) -> bool:
        """The feedback is in. False when the summary was not waiting for it, or is gone."""
        return self._move(
            "UPDATE summaries SET status = 'done', feedback = ?, error = NULL WHERE id = ? AND status = 'judging' RETURNING paragraph_id",
            feedback.model_dump_json(),
            summary_id,
        )

    def fail_summary(self, summary_id: int, error: str) -> bool:
        """The feedback could not be had; `error` says why."""
        return self._move("UPDATE summaries SET status = 'failed', error = ? WHERE id = ? AND status = 'judging' RETURNING paragraph_id", error, summary_id)

    def rejudge_summary(self, summary_id: int) -> bool:
        """A failed summary waits for its feedback again. False for any other, so only one of two tries at once wins."""
        return self._move("UPDATE summaries SET status = 'judging', error = NULL WHERE id = ? AND status = 'failed' RETURNING paragraph_id", summary_id)

    def remove_failed_summary(self, summary_id: int) -> bool:
        """Only a summary whose feedback failed can go; a judged one is the session's record."""
        return self._move("DELETE FROM summaries WHERE id = ? AND status = 'failed' RETURNING paragraph_id", summary_id)

    def fail_unfinished_summaries(self, error: str) -> None:
        """Every summary still waiting, for when nothing can be judging one: the process that was is gone. No one is
        listening yet, so nothing is announced."""
        with self._db.connect() as conn:
            conn.execute("UPDATE summaries SET status = 'failed', error = ? WHERE status = 'judging'", (error,))

    def get_summary(self, summary_id: int, viewer_id: int) -> Summary | None:
        """As `viewer_id` sees it."""
        rows = self._summaries("s.id = ?", summary_id, viewer_id)
        return rows[0] if rows else None

    def list_summaries(self, session_id: int, viewer_id: int) -> list[Summary]:
        """In the order they were made, so they stack under each paragraph, as `viewer_id` sees them."""
        return self._summaries("p.session_id = ?", session_id, viewer_id)

    def _summaries(self, where: str, key: int, viewer_id: int) -> list[Summary]:
        with self._db.connect() as conn:
            rows = conn.execute(
                f"""SELECT s.id, s.created_at, s.paragraph_id, s.user_text, s.seconds, s.status, s.feedback, s.error,
                           u.username AS speaker, s.user_id IS NOT NULL AND s.user_id = ? AS mine
                    FROM summaries s JOIN paragraphs p ON p.id = s.paragraph_id LEFT JOIN users u ON u.id = s.user_id
                    WHERE {where} ORDER BY s.id""",
                (viewer_id, key),
            ).fetchall()
        return [_summary(row) for row in rows]

    def _move(self, statement: str, *params: object) -> bool:
        """Runs one UPDATE or DELETE ... RETURNING paragraph_id on a summary and announces it if a row moved."""
        with self._db.connect() as conn:
            rows = conn.execute(statement, params).fetchall()  # all of them, so the statement is done before the commit
        if not rows:
            return False
        self._announce(rows[0]["paragraph_id"])
        return True

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


def _summary(row) -> Summary:
    feedback = row["feedback"]
    return Summary(
        **{**dict(row), "mine": bool(row["mine"]), "feedback": SummaryFeedback.model_validate_json(feedback) if feedback else None}
    )
