"""What the coaches leave behind: asks, sentences made with an expression, paragraphs read aloud."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models import Ask, Correction, Example, PhraseCard, Reading

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

    def _select(self, table: str, session_id: int | None, order: str) -> list:
        """A session_id narrows to that session; None lists every row."""
        sql, params = f"SELECT * FROM {table}", ()
        if session_id is not None:
            sql, params = sql + " WHERE session_id = ?", (session_id,)
        with self._db.connect() as conn:
            return conn.execute(f"{sql} ORDER BY id {order}", params).fetchall()

    # One question asked aloud mid-conversation, and its answer.

    def add_ask(self, session_id: int | None, user_text: str, coach_text: str, seconds: float) -> Ask:
        fields = dict(session_id=session_id, user_text=user_text, coach_text=coach_text, seconds=seconds)
        ask_id, created_at = self._insert("asks", **fields)
        return Ask(id=ask_id, created_at=created_at, **fields)

    def list_asks(self, session_id: int | None = None) -> list[Ask]:
        """Newest first."""
        return [
            Ask(**{**dict(row), "card": PhraseCard.model_validate_json(row["card_json"]) if row["card_json"] else None})
            for row in self._select("asks", session_id, "DESC")
        ]

    def set_ask_card(self, ask_id: int, card: PhraseCard) -> None:
        with self._db.connect() as conn:
            conn.execute("UPDATE asks SET card_json = ? WHERE id = ?", (card.model_dump_json(), ask_id))

    # A sentence made with an expression, and the coach's echo.

    def add_example(self, session_id: int, expression: str, user_text: str, coach_text: str, seconds: float) -> Example:
        fields = dict(session_id=session_id, expression=expression, user_text=user_text, coach_text=coach_text, seconds=seconds)
        example_id, created_at = self._insert("examples", **fields)
        return Example(id=example_id, created_at=created_at, **fields)

    def list_examples(self, session_id: int) -> list[Example]:
        """In the order they were made, so they stack under each expression."""
        return [Example(**dict(row)) for row in self._select("examples", session_id, "ASC")]

    # One paragraph read aloud, and what the assessor stopped the reader on.

    def add_reading(
        self,
        session_id: int | None,
        paragraph: str,
        user_text: str,
        coach_text: str,
        seconds: float,
        corrections: list[Correction],
    ) -> Reading:
        fields = dict(session_id=session_id, paragraph=paragraph, user_text=user_text, coach_text=coach_text, seconds=seconds)
        payload = json.dumps([c.model_dump() for c in corrections])
        reading_id, created_at = self._insert("readings", **fields, corrections_json=payload)
        return Reading(id=reading_id, created_at=created_at, corrections=corrections, **fields)

    def list_readings(self, session_id: int | None = None) -> list[Reading]:
        """Newest first. Readings saved before corrections were kept carry None."""
        readings = []
        for row in self._select("readings", session_id, "DESC"):
            saved = row["corrections_json"]
            corrections = [Correction.model_validate(c) for c in json.loads(saved)] if saved else None
            readings.append(Reading(**{**dict(row), "corrections": corrections}))
        return readings
