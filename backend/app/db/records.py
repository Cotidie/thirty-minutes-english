"""What the coaches leave behind: sentences made with an expression, paragraphs read aloud or summed up."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models import Correction, Example, Reading, Summary, SummaryFeedback

if TYPE_CHECKING:
    from app.db import Database


class RecordRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def _insert(self, table: str, **values) -> tuple[int, datetime]:
        created_at = datetime.now(UTC)
        values = {"created_at": created_at.isoformat(), **values}
        columns = ", ".join(values)
        marks = ", ".join("?" * len(values))
        with self._db.connect() as conn:
            cur = conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values()))
        assert cur.lastrowid is not None
        return cur.lastrowid, created_at

    def _select(self, table: str, session_id: int, order: str) -> list:
        with self._db.connect() as conn:
            return conn.execute(f"SELECT * FROM {table} WHERE session_id = ? ORDER BY id {order}", (session_id,)).fetchall()

    # A sentence made with an expression, and the coach's echo.

    def add_example(self, session_id: int, expression: str, user_text: str, coach_text: str, seconds: float) -> Example:
        fields = dict(session_id=session_id, expression=expression, user_text=user_text, coach_text=coach_text, seconds=seconds)
        example_id, created_at = self._insert("examples", **fields)
        return Example(id=example_id, created_at=created_at, **fields)

    def list_examples(self, session_id: int) -> list[Example]:
        """In the order they were made, so they stack under each expression."""
        return [Example(**dict(row)) for row in self._select("examples", session_id, "ASC")]

    # One paragraph summed up out loud, and the coach's judgment of it.

    def add_summary(self, session_id: int, paragraph: str, user_text: str, feedback: SummaryFeedback, seconds: float) -> Summary:
        fields = dict(session_id=session_id, paragraph=paragraph, user_text=user_text, seconds=seconds)
        summary_id, created_at = self._insert("summaries", **fields, feedback_json=feedback.model_dump_json())
        return Summary(id=summary_id, created_at=created_at, feedback=feedback, **fields)

    def list_summaries(self, session_id: int) -> list[Summary]:
        """In the order they were made, so they stack under each paragraph."""
        rows = [dict(row) for row in self._select("summaries", session_id, "ASC")]
        return [Summary(**row, feedback=SummaryFeedback.model_validate_json(row.pop("feedback_json"))) for row in rows]

    # One paragraph read aloud, and what the assessor stopped the reader on.

    def add_reading(
        self,
        session_id: int,
        paragraph: str,
        user_text: str,
        seconds: float,
        corrections: list[Correction],
    ) -> Reading:
        fields = dict(session_id=session_id, paragraph=paragraph, user_text=user_text, seconds=seconds)
        payload = json.dumps([c.model_dump() for c in corrections])
        reading_id, created_at = self._insert("readings", **fields, corrections_json=payload)
        return Reading(id=reading_id, created_at=created_at, corrections=corrections, **fields)

    def list_readings(self, session_id: int) -> list[Reading]:
        """Newest first. Readings saved before corrections were kept carry None; the pause
        findings older readings hold are left out."""
        readings = []
        for row in self._select("readings", session_id, "DESC"):
            saved = row["corrections_json"]
            corrections = [Correction.model_validate(c) for c in json.loads(saved) if c.get("kind") != "phrasing"] if saved else None
            readings.append(Reading(**{**dict(row), "corrections": corrections}))
        return readings
