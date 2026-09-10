import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.exclusions import Exclusions
from app.models import Session, SessionContent, SessionSummary


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
        return cur.rowcount > 0

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
