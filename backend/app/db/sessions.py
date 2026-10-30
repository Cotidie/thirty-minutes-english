"""Sessions and what belongs to them: the article's paragraphs, the words, the expressions taught
from the corpus (and the ones swapped out), the stars on those, and the note."""

import json
import random
import re
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.db.expressions import COLUMNS as EXPRESSION_COLUMNS
from app.db import topics
from app.db.expressions import expression_from
from app.db.shares import VISIBLE_SESSIONS
from app.models import Article, Category, Draft, Expression, Figure, Note, Paragraph, Question, SentencePair, Session, SessionContent, SessionSummary, Source, Stars, VocabularyItem

if TYPE_CHECKING:
    from app.db import Database
    from app.pictures.illustrator import PictureField
    from app.pictures.scenes import Scene

# The vocabulary column each picture of a word lives in.
PICTURE_COLUMNS = {"image": "picture_id", "example_image": "example_picture_id"}
# A session read with its topic's text.
WITH_TOPIC = "sessions s JOIN topics t ON t.id = s.topic_id"


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

    def create(self, draft: Draft, expression_ids: Sequence[int], created_by: int | None = None) -> Session:
        """Stores the draft with the corpus expressions it teaches, in that order."""
        article = draft.article
        with self._db.connect() as conn:
            now = datetime.now(UTC).isoformat()
            cur = conn.execute(
                "INSERT INTO sessions (created_at, topic_id, title, questions, sources, translation, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, topics.ensure(conn, draft.topic, Category.TYPED, now), article.title, _json(article.questions), _json(article.sources),
                 _json(article.translation), created_by),
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
            row = conn.execute(f"SELECT s.*, t.text AS topic FROM {WITH_TOPIC} WHERE s.id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            paragraphs = conn.execute("SELECT id, text FROM paragraphs WHERE session_id = ? ORDER BY position", (session_id,)).fetchall()
            expressions = conn.execute(
                f"SELECT {EXPRESSION_COLUMNS} FROM session_expressions se JOIN expressions e ON e.id = se.expression_id"
                " WHERE se.session_id = ? ORDER BY se.position",
                (session_id,),
            ).fetchall()
            words = conn.execute("SELECT * FROM vocabulary WHERE session_id = ? ORDER BY position", (session_id,)).fetchall()
            figures = conn.execute(
                "SELECT * FROM figures WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        article = Article(
            title=row["title"],
            paragraphs=[Paragraph(id=p["id"], text=p["text"]) for p in paragraphs],
            questions=[Question(**q) for q in json.loads(row["questions"])],
            sources=[Source(**s) for s in json.loads(row["sources"])],
            translation=[SentencePair(**t) for t in json.loads(row["translation"])],
            figures=[
                Figure(id=f["id"], paragraph_id=f["paragraph_id"], image=f"{f['picture_id']}.png", caption=f["caption"],
                       source_url=f["source_url"], credit=f["credit"])
                for f in figures
            ],
        )
        content = SessionContent(
            topic=row["topic"], expressions=[expression_from(e) for e in expressions], article=article, vocabulary=[_word(w) for w in words]
        )
        return Session(id=row["id"], created_at=row["created_at"], topic=row["topic"], content=content)

    def swap_expression(
        self, session_id: int, expression_id: int, rng: random.Random | None = None, seen_by: int | None = None
    ) -> Expression | None:
        """The expression put in place of `expression_id`, picked as a new session picks one for `seen_by` but never
        one this session has had; the one swapped out counts as used here, and its star goes.
        None when the session does not teach `expression_id`, or the corpus has nothing else to offer."""
        had = self._had(session_id)
        if expression_id not in had:
            return None
        picked = self._db.expressions.pick(1, rng or random.Random(), exclude=had, seen_by=seen_by)
        if not picked:
            return None
        with self._db.connect() as conn:
            row = conn.execute(
                "DELETE FROM session_expressions WHERE session_id = ? AND expression_id = ? RETURNING position", (session_id, expression_id)
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "INSERT INTO session_expressions (session_id, expression_id, position) VALUES (?, ?, ?)", (session_id, picked[0].id, row[0])
            )
            conn.execute(
                "INSERT INTO swapped_expressions (session_id, expression_id, swapped_at) VALUES (?, ?, ?)",
                (session_id, expression_id, datetime.now(UTC).isoformat()),
            )
        return picked[0]

    def add_expression(self, session_id: int, rng: random.Random | None = None, seen_by: int | None = None) -> Expression | None:
        """One more expression taught after the others, picked as `swap_expression` picks one.
        None when there is no such session, or the corpus has nothing else to offer."""
        if not self.exists(session_id):
            return None
        picked = self._db.expressions.pick(1, rng or random.Random(), exclude=self._had(session_id), seen_by=seen_by)
        if not picked:
            return None
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO session_expressions (session_id, expression_id, position)"
                " SELECT ?, ?, COALESCE(MAX(position) + 1, 0) FROM session_expressions WHERE session_id = ?",
                (session_id, picked[0].id, session_id),
            )
        return picked[0]

    def _had(self, session_id: int) -> set[int]:
        """The expressions the session teaches or swapped out."""
        with self._db.connect() as conn:
            return {
                row[0] for row in conn.execute(
                    "SELECT expression_id FROM session_expressions WHERE session_id = ?"
                    " UNION SELECT expression_id FROM swapped_expressions WHERE session_id = ?",
                    (session_id, session_id),
                )
            }

    def exists(self, session_id: int) -> bool:
        with self._db.connect() as conn:
            return conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None

    def list_visible(self, user_id: int) -> list[SessionSummary]:
        """The sessions the account made or had shared with it, newest first, each saying whose it is."""
        with self._db.connect() as conn:
            rows = conn.execute(
                f"""SELECT s.id, s.created_at, t.text AS topic, s.title, s.created_by = ? AS mine,
                           CASE WHEN s.created_by = ? THEN NULL ELSE u.email END AS shared_by
                    FROM {WITH_TOPIC} LEFT JOIN users u ON u.id = s.created_by
                    WHERE s.id IN ({VISIBLE_SESSIONS})
                    ORDER BY s.id DESC""",
                (user_id, user_id, user_id, user_id),
            ).fetchall()
        return [SessionSummary(**dict(row)) for row in rows]

    def viewpoint(self, session_id: int, user_id: int) -> tuple[bool, str | None]:
        """Whether the account made the session, and if not, the email of who did."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT s.created_by, u.email FROM sessions s LEFT JOIN users u ON u.id = s.created_by WHERE s.id = ?", (session_id,)
            ).fetchone()
        if row is None or row["created_by"] == user_id:
            return row is not None, None
        return False, row["email"]

    def delete(self, session_id: int) -> list[int] | None:
        """The ids of the pictures the session showed (its words', then its figures'), whose files the caller removes;
        None when there was no such session. Everything the session owns goes with it; the corpus and the picture rows stay."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT picture_id, example_picture_id FROM vocabulary WHERE session_id = ? ORDER BY position", (session_id,)
            ).fetchall()
            figures = conn.execute(
                "SELECT picture_id FROM figures WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
            if conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,)).rowcount == 0:
                return None
        return [picture for row in rows for picture in row if picture is not None] + [f[0] for f in figures]

    def add_figure(
        self, session_id: int, paragraph_id: int | None, picture_id: int, caption: str, source_url: str | None, credit: str | None
    ) -> int:
        """Shows the picture under the paragraph, or under the title as the article's cover when `paragraph_id` is None.
        Raises KeyError when the session is gone (it was deleted while the picture came)."""
        try:
            with self._db.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO figures (session_id, paragraph_id, picture_id, caption, source_url, credit) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, paragraph_id, picture_id, caption, source_url, credit),
                )
        except sqlite3.IntegrityError:
            raise KeyError(session_id) from None
        assert cur.lastrowid is not None
        return cur.lastrowid

    def recent_topics(self, limit: int) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT t.text AS topic, MAX(s.id) AS last_id FROM {WITH_TOPIC} GROUP BY s.topic_id ORDER BY last_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [row["topic"] for row in rows]

    def used_words(self, limit_sessions: int = 40, seen_by: int | None = None) -> tuple[str, ...]:
        """Distinct words of the most recent sessions, newest session first; with `seen_by`, of the sessions
        that account made or had shared with it."""
        recent, params = (
            ("SELECT id FROM sessions ORDER BY id DESC LIMIT ?", (limit_sessions,))
            if seen_by is None
            else (f"SELECT id FROM ({VISIBLE_SESSIONS}) ORDER BY id DESC LIMIT ?", (seen_by, seen_by, limit_sessions))
        )
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT v.word FROM vocabulary v JOIN ({recent}) s ON s.id = v.session_id ORDER BY s.id DESC, v.position",
                params,
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
