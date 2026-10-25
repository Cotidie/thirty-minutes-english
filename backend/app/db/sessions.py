"""Sessions and what belongs to them: the article's paragraphs, the words, the expressions taught
from the corpus, the stars on those, and the note."""

import json
import re
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.db.expressions import COLUMNS as EXPRESSION_COLUMNS
from app.db.expressions import expression_from
from app.models import Article, Draft, Note, Paragraph, Question, SentencePair, Session, SessionContent, SessionSummary, Source, Stars, VocabularyItem

if TYPE_CHECKING:
    from app.db import Database
    from app.pictures.illustrator import PictureField
    from app.pictures.scenes import Scene

# The vocabulary column each picture of a word lives in.
PICTURE_COLUMNS = {"image": "picture_id", "example_image": "example_picture_id"}


def paragraphs_of(body: str) -> list[str]:
    """The body cut at blank lines, each paragraph trimmed, empty ones dropped."""
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _picture(picture_id: int | None) -> str | None:
    return f"{picture_id}.png" if picture_id is not None else None


def _word(row: sqlite3.Row) -> VocabularyItem:
    return VocabularyItem(
        id=row["id"], word=row["word"], pos=row["pos"], definition=row["definition"], synonyms=json.loads(row["synonyms"]),
        example=row["example"], korean=row["korean"], scene=row["scene"], caption=row["caption"],
        image=_picture(row["picture_id"]), example_image=_picture(row["example_picture_id"]),
    )


def _json(models: list) -> str:
    return json.dumps([m.model_dump() for m in models], ensure_ascii=False)


class SessionRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def create(self, draft: Draft, expression_ids: Sequence[int]) -> Session:
        """Stores the draft with the corpus expressions it teaches, in that order."""
        article = draft.article
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (created_at, topic, title, questions, sources, translation) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now(UTC).isoformat(), draft.topic, article.title, _json(article.questions), _json(article.sources), _json(article.translation)),
            )
            session_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO paragraphs (session_id, position, text) VALUES (?, ?, ?)",
                [(session_id, i, text) for i, text in enumerate(paragraphs_of(article.body))],
            )
            conn.executemany(
                "INSERT INTO vocabulary (session_id, position, word, pos, definition, synonyms, example, korean, scene, caption)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (session_id, i, v.word, v.pos, v.definition, json.dumps(v.synonyms, ensure_ascii=False), v.example, v.korean, v.scene, v.caption)
                    for i, v in enumerate(draft.vocabulary)
                ],
            )
            conn.executemany(
                "INSERT INTO session_expressions (session_id, expression_id, position) VALUES (?, ?, ?)",
                [(session_id, expression_id, i) for i, expression_id in enumerate(expression_ids)],
            )
        session = self.get(session_id)
        assert session is not None
        return session

    def get(self, session_id: int) -> Session | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            paragraphs = conn.execute("SELECT id, text FROM paragraphs WHERE session_id = ? ORDER BY position", (session_id,)).fetchall()
            expressions = conn.execute(
                f"SELECT {EXPRESSION_COLUMNS} FROM session_expressions se JOIN expressions e ON e.id = se.expression_id"
                " WHERE se.session_id = ? ORDER BY se.position",
                (session_id,),
            ).fetchall()
            words = conn.execute("SELECT * FROM vocabulary WHERE session_id = ? ORDER BY position", (session_id,)).fetchall()
        article = Article(
            title=row["title"],
            paragraphs=[Paragraph(id=p["id"], text=p["text"]) for p in paragraphs],
            questions=[Question(**q) for q in json.loads(row["questions"])],
            sources=[Source(**s) for s in json.loads(row["sources"])],
            translation=[SentencePair(**t) for t in json.loads(row["translation"])],
        )
        content = SessionContent(
            topic=row["topic"], expressions=[expression_from(e) for e in expressions], article=article, vocabulary=[_word(w) for w in words]
        )
        return Session(id=row["id"], created_at=row["created_at"], topic=row["topic"], content=content)

    def exists(self, session_id: int) -> bool:
        with self._db.connect() as conn:
            return conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None

    def list_all(self) -> list[SessionSummary]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT id, created_at, topic, title FROM sessions ORDER BY id DESC").fetchall()
        return [SessionSummary(**dict(row)) for row in rows]

    def delete(self, session_id: int) -> list[int] | None:
        """The ids of the pictures the session's words showed, whose files the caller removes; None when there was no such session.
        Everything the session owns goes with it; the corpus and the picture rows stay."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT picture_id, example_picture_id FROM vocabulary WHERE session_id = ? ORDER BY position", (session_id,)
            ).fetchall()
            if conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,)).rowcount == 0:
                return None
        return [picture for row in rows for picture in row if picture is not None]

    def recent_topics(self, limit: int) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT topic, MAX(id) AS last_id FROM sessions GROUP BY topic ORDER BY last_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [row["topic"] for row in rows]

    def used_words(self, limit_sessions: int = 40) -> tuple[str, ...]:
        """Distinct words of the most recent sessions, newest session first."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT v.word FROM vocabulary v JOIN (SELECT id FROM sessions ORDER BY id DESC LIMIT ?) s ON s.id = v.session_id"
                " ORDER BY s.id DESC, v.position",
                (limit_sessions,),
            ).fetchall()
        return tuple(dict.fromkeys(row["word"] for row in rows))

    def replace_picture(self, vocabulary_id: int, field: "PictureField", picture_id: int, scene: "Scene | None" = None) -> int | None:
        """Points the word's `field` at `picture_id` (and takes `scene` with it, when given); the picture it showed before.
        Read and write share one write lock, so pictures landing on the same word at once do not undo each other.
        Raises KeyError when there is no such word."""
        column = PICTURE_COLUMNS[field]
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(f"SELECT {column} FROM vocabulary WHERE id = ?", (vocabulary_id,)).fetchone()
            if row is None:
                raise KeyError(vocabulary_id)
            if scene is None:
                conn.execute(f"UPDATE vocabulary SET {column} = ? WHERE id = ?", (picture_id, vocabulary_id))
            else:
                conn.execute(
                    f"UPDATE vocabulary SET {column} = ?, scene = ?, caption = ? WHERE id = ?",
                    (picture_id, scene.text, scene.caption or None, vocabulary_id),
                )
        return row[0]

    def session_of_paragraph(self, paragraph_id: int) -> int | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT session_id FROM paragraphs WHERE id = ?", (paragraph_id,)).fetchone()
        return row[0] if row else None

    def get_stars(self, session_id: int) -> Stars:
        with self._db.connect() as conn:
            expressions = conn.execute(
                "SELECT expression_id FROM session_expressions WHERE session_id = ? AND starred ORDER BY position", (session_id,)
            ).fetchall()
            words = conn.execute("SELECT id FROM vocabulary WHERE session_id = ? AND starred ORDER BY position", (session_id,)).fetchall()
        return Stars(expressions=[r[0] for r in expressions], words=[r[0] for r in words])

    def set_stars(self, session_id: int, stars: Stars) -> Stars:
        """The session's stars become exactly `stars`; ids that are not the session's are ignored."""
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE session_expressions SET starred = expression_id IN (SELECT value FROM json_each(?)) WHERE session_id = ?",
                (json.dumps(stars.expressions), session_id),
            )
            conn.execute(
                "UPDATE vocabulary SET starred = id IN (SELECT value FROM json_each(?)) WHERE session_id = ?",
                (json.dumps(stars.words), session_id),
            )
        return self.get_stars(session_id)

    def get_note(self, session_id: int) -> Note:
        with self._db.connect() as conn:
            row = conn.execute("SELECT note FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return Note(text=row["note"] if row else "")

    def set_note(self, session_id: int, note: Note) -> Note:
        with self._db.connect() as conn:
            conn.execute("UPDATE sessions SET note = ? WHERE id = ?", (note.text, session_id))
        return self.get_note(session_id)
