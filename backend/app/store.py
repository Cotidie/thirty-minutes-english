import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.exclusions import Exclusions
from app.models import Ask, Correction, Example, PhraseCard, Reading, Session, SessionContent, SessionSummary, Stars


class SessionStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS asks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    session_id INTEGER,
                    user_text TEXT NOT NULL,
                    coach_text TEXT NOT NULL,
                    seconds REAL NOT NULL DEFAULT 0,
                    card_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    session_id INTEGER,
                    paragraph TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    coach_text TEXT NOT NULL,
                    seconds REAL NOT NULL DEFAULT 0,
                    corrections_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS examples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    session_id INTEGER NOT NULL,
                    expression TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    coach_text TEXT NOT NULL,
                    seconds REAL NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stars (
                    session_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    item TEXT NOT NULL,
                    PRIMARY KEY (session_id, kind, item)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topic_days (
                    day TEXT PRIMARY KEY,
                    topics_json TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, content: SessionContent) -> Session:
        created_at = datetime.now(UTC)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (created_at, topic, title, content_json) VALUES (?, ?, ?, ?)",
                (created_at.isoformat(), content.topic, content.article.title, content.model_dump_json()),
            )
            session_id = cur.lastrowid
        assert session_id is not None
        return Session(id=session_id, created_at=created_at, topic=content.topic, content=content)

    def list_all(self) -> list[SessionSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, topic, title FROM sessions ORDER BY id DESC"
            ).fetchall()
        return [SessionSummary(**dict(row)) for row in rows]

    def get(self, session_id: int) -> Session | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, created_at, topic, content_json FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            created_at=row["created_at"],
            topic=row["topic"],
            content=SessionContent.model_validate_json(row["content_json"]),
        )

    def delete(self, session_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.execute("DELETE FROM asks WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM readings WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM stars WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM examples WHERE session_id = ?", (session_id,))
        return cur.rowcount > 0

    def get_stars(self, session_id: int) -> Stars:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT kind, item FROM stars WHERE session_id = ? ORDER BY rowid", (session_id,)
            ).fetchall()
        return Stars(
            expressions=[r["item"] for r in rows if r["kind"] == "expression"],
            words=[r["item"] for r in rows if r["kind"] == "word"],
        )

    def set_stars(self, session_id: int, stars: Stars) -> Stars:
        rows = [(session_id, "expression", e) for e in dict.fromkeys(stars.expressions)]
        rows += [(session_id, "word", w) for w in dict.fromkeys(stars.words)]
        with self._connect() as conn:
            conn.execute("DELETE FROM stars WHERE session_id = ?", (session_id,))
            conn.executemany("INSERT INTO stars (session_id, kind, item) VALUES (?, ?, ?)", rows)
        return self.get_stars(session_id)

    def recent_topics(self, limit: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT topic, MAX(id) AS last_id FROM sessions GROUP BY topic ORDER BY last_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row["topic"] for row in rows]

    def used_items(self, limit_sessions: int = 40) -> Exclusions:
        """Distinct expressions and words from the most recent sessions, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT content_json FROM sessions ORDER BY id DESC LIMIT ?", (limit_sessions,)
            ).fetchall()
        expressions: dict[str, None] = {}
        words: dict[str, None] = {}
        for row in rows:
            content = SessionContent.model_validate_json(row["content_json"])
            expressions.update((e.phrase, None) for e in content.expressions)
            words.update((v.word, None) for v in content.vocabulary)
        return Exclusions(tuple(expressions), tuple(words))

    # --- asks: one question asked aloud mid-conversation, and its answer -----

    def add_ask(self, session_id: int | None, user_text: str, coach_text: str, seconds: float) -> Ask:
        created_at = datetime.now(UTC)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO asks (created_at, session_id, user_text, coach_text, seconds)"
                " VALUES (?, ?, ?, ?, ?)",
                (created_at.isoformat(), session_id, user_text, coach_text, seconds),
            )
            ask_id = cur.lastrowid
        assert ask_id is not None
        return Ask(
            id=ask_id,
            created_at=created_at,
            session_id=session_id,
            user_text=user_text,
            coach_text=coach_text,
            seconds=seconds,
        )

    def list_asks(self, session_id: int | None = None) -> list[Ask]:
        """Newest first. A session_id narrows to that session; None lists every ask."""
        sql = "SELECT * FROM asks"
        params: tuple = ()
        if session_id is not None:
            sql += " WHERE session_id = ?"
            params = (session_id,)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY id DESC", params).fetchall()
        return [_ask(row) for row in rows]

    def set_ask_card(self, ask_id: int, card: PhraseCard) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE asks SET card_json = ? WHERE id = ?", (card.model_dump_json(), ask_id))


    # --- examples: a sentence made with an expression, and the coach's echo --

    def add_example(
        self, session_id: int, expression: str, user_text: str, coach_text: str, seconds: float
    ) -> Example:
        created_at = datetime.now(UTC)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO examples (created_at, session_id, expression, user_text, coach_text, seconds)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (created_at.isoformat(), session_id, expression, user_text, coach_text, seconds),
            )
            example_id = cur.lastrowid
        assert example_id is not None
        return Example(
            id=example_id,
            created_at=created_at,
            session_id=session_id,
            expression=expression,
            user_text=user_text,
            coach_text=coach_text,
            seconds=seconds,
        )

    def list_examples(self, session_id: int) -> list[Example]:
        """In the order they were made, so they stack under each expression."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM examples WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [Example(**dict(row)) for row in rows]

    # --- readings: one paragraph read aloud, and what the coach stopped on --

    def add_reading(
        self, session_id: int | None, paragraph: str, user_text: str, coach_text: str, seconds: float
    ) -> Reading:
        created_at = datetime.now(UTC)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO readings (created_at, session_id, paragraph, user_text, coach_text, seconds)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (created_at.isoformat(), session_id, paragraph, user_text, coach_text, seconds),
            )
            reading_id = cur.lastrowid
        assert reading_id is not None
        return Reading(
            id=reading_id,
            created_at=created_at,
            session_id=session_id,
            paragraph=paragraph,
            user_text=user_text,
            coach_text=coach_text,
            seconds=seconds,
        )

    def list_readings(self, session_id: int | None = None) -> list[Reading]:
        """Newest first. A session_id narrows to that session; None lists every reading."""
        sql = "SELECT * FROM readings"
        params: tuple = ()
        if session_id is not None:
            sql += " WHERE session_id = ?"
            params = (session_id,)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY id DESC", params).fetchall()
        return [_reading(row) for row in rows]

    def set_reading_corrections(self, reading_id: int, corrections: list[Correction]) -> None:
        payload = json.dumps([c.model_dump() for c in corrections])
        with self._connect() as conn:
            conn.execute("UPDATE readings SET corrections_json = ? WHERE id = ?", (payload, reading_id))


    # --- topic_days: the news half of one day's suggestions ------------------

    def get_daily_topics(self, day: str) -> list[str] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT topics_json FROM topic_days WHERE day = ?", (day,)).fetchone()
        return json.loads(row["topics_json"]) if row else None

    def set_daily_topics(self, day: str, topics: list[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO topic_days (day, topics_json) VALUES (?, ?)"
                " ON CONFLICT(day) DO UPDATE SET topics_json = excluded.topics_json",
                (day, json.dumps(topics, ensure_ascii=False)),
            )


def _reading(row: sqlite3.Row) -> Reading:
    saved = row["corrections_json"]
    return Reading(
        id=row["id"],
        created_at=row["created_at"],
        session_id=row["session_id"],
        paragraph=row["paragraph"],
        user_text=row["user_text"],
        coach_text=row["coach_text"],
        seconds=row["seconds"],
        corrections=[Correction.model_validate(c) for c in json.loads(saved)] if saved else None,
    )


def _ask(row: sqlite3.Row) -> Ask:
    card = row["card_json"]
    return Ask(
        id=row["id"],
        created_at=row["created_at"],
        session_id=row["session_id"],
        user_text=row["user_text"],
        coach_text=row["coach_text"],
        seconds=row["seconds"],
        card=PhraseCard.model_validate_json(card) if card else None,
    )
