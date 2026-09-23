"""Sessions, the stars on them, and what earlier sessions already taught."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.generation.exclusions import Exclusions
from app.models import Session, SessionContent, SessionSummary, Stars, VocabularyItem

if TYPE_CHECKING:
    from app.db import Database

# Rows that belong to a session and go with it.
OWNED_TABLES = ("asks", "readings", "stars", "examples")


class SessionRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def create(self, content: SessionContent) -> Session:
        created_at = datetime.now(UTC)
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (created_at, topic, title, content_json) VALUES (?, ?, ?, ?)",
                (created_at.isoformat(), content.topic, content.article.title, content.model_dump_json()),
            )
        assert cur.lastrowid is not None
        return Session(id=cur.lastrowid, created_at=created_at, topic=content.topic, content=content)

    def get(self, session_id: int) -> Session | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id, created_at, topic, content_json FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        content = SessionContent.model_validate_json(row["content_json"])
        return Session(id=row["id"], created_at=row["created_at"], topic=row["topic"], content=content)

    def exists(self, session_id: int) -> bool:
        with self._db.connect() as conn:
            return conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None

    def list_all(self) -> list[SessionSummary]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT id, created_at, topic, title FROM sessions ORDER BY id DESC").fetchall()
        return [SessionSummary(**dict(row)) for row in rows]

    def delete(self, session_id: int) -> bool:
        with self._db.connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            for table in OWNED_TABLES:
                conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
        return cur.rowcount > 0

    def replace_vocabulary_item(self, session_id: int, index: int, item: VocabularyItem) -> VocabularyItem | None:
        """The item that was stored at `index`, now replaced by `item`; None when there is no such word.
        Read and write share one write lock, so two redraws finishing at once do not undo each other."""
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT content_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            content = SessionContent.model_validate_json(row["content_json"])
            if not 0 <= index < len(content.vocabulary):
                return None
            vocabulary = list(content.vocabulary)
            previous, vocabulary[index] = vocabulary[index], item
            content = content.model_copy(update={"vocabulary": vocabulary})
            conn.execute("UPDATE sessions SET content_json = ? WHERE id = ?", (content.model_dump_json(), session_id))
        return previous

    def get_stars(self, session_id: int) -> Stars:
        with self._db.connect() as conn:
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
        with self._db.connect() as conn:
            conn.execute("DELETE FROM stars WHERE session_id = ?", (session_id,))
            conn.executemany("INSERT INTO stars (session_id, kind, item) VALUES (?, ?, ?)", rows)
        return self.get_stars(session_id)

    def recent_topics(self, limit: int) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT topic, MAX(id) AS last_id FROM sessions GROUP BY topic ORDER BY last_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row["topic"] for row in rows]

    def used_items(self, limit_sessions: int = 40) -> Exclusions:
        """Distinct expressions and words from the most recent sessions, newest first."""
        with self._db.connect() as conn:
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
