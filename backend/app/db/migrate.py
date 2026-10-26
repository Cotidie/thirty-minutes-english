"""Brings a v1 file up to schema v2. v1 kept each session as one JSON blob and pointed at paragraphs,
expressions and words by their text; v2 gives each a row and points by id. The tables move in one
transaction; the picture files take their rows' ids only once it has committed."""

import json
import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.db import schema, topics
from app.db.expressions import upsert as upsert_expression
from app.db.sessions import paragraphs_of
from app.generation.exclusions import key
from app.models import ArticleDraft, Category, VocabularyDraft

log = logging.getLogger(__name__)

# Tables whose AUTOINCREMENT counter carries over, so ids of deleted rows are not handed out again.
COUNTED = ("sessions", "readings", "summaries", "examples")


@dataclass
class Report:
    sessions: int = 0
    expressions: int = 0
    pictures_renamed: int = 0
    pictures_missing: int = 0
    readings_dropped: int = 0
    summaries_dropped: int = 0
    examples_dropped: int = 0
    orphan_files: int = 0


def is_v1(conn: sqlite3.Connection) -> bool:
    return conn.execute("PRAGMA user_version").fetchone()[0] == 0 and any(
        column["name"] == "content_json" for column in conn.execute("PRAGMA table_info(sessions)")
    )


def backup(path: Path, version: int) -> Path:
    """A copy of the file, still at `version`, beside it and dated."""
    target = path.with_name(f"{path.name}.bak-v{version}-{date.today():%Y-%m-%d}")
    shutil.copy2(path, target)
    return target


def migrate_v1(conn: sqlite3.Connection, images_dir: Path | None, renames: Path | None = None) -> Report:
    """`renames` gets the old-to-new file name of every picture, written before the commit, so a crash
    before the renames, or a return to the v1 copy, can be undone by hand."""
    return Migration(conn, images_dir, renames).run()


class Migration:
    def __init__(self, conn: sqlite3.Connection, images_dir: Path | None, renames: Path | None = None) -> None:
        self.conn = conn
        self.images_dir = images_dir
        self.renames = renames
        self.files = {p.name for p in images_dir.iterdir() if p.is_file()} if images_dir and images_dir.is_dir() else set()
        self.pictures: dict[str, int] = {}  # v1 file name -> its pictures row
        self.referenced: set[str] = set()
        self.report = Report()

    def run(self) -> Report:
        conn = self.conn
        conn.execute("BEGIN")
        try:
            old = [name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
            for name in old:
                conn.execute(f'ALTER TABLE "{name}" RENAME TO "{name}_v1"')
            schema.create(conn)
            self._app_state()
            conn.execute("INSERT INTO pictures (created_at, model, seconds, cost) SELECT created_at, model, seconds, cost FROM image_stats_v1 ORDER BY id")
            for session in conn.execute("SELECT * FROM sessions_v1 ORDER BY id").fetchall():
                self._session(session)
            self._readings()
            self._summaries()
            self._examples()
            self._carry_counters()
            for name in old:
                conn.execute(f'DROP TABLE "{name}_v1"')
            self.report.expressions = conn.execute("SELECT COUNT(*) FROM expressions").fetchone()[0]
            if self.renames:
                self.renames.write_text(json.dumps({name: f"{pid}.png" for name, pid in self.pictures.items()}, indent=1))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        self.report.orphan_files = len(self.files - self.referenced)
        self._rename_files()
        return self.report

    def _app_state(self) -> None:
        conn = self.conn
        conn.execute("INSERT INTO settings SELECT key, value FROM settings_v1")
        conn.execute("INSERT INTO model_pins SELECT source, model, pinned_at FROM model_pins_v1")
        for day, stored in conn.execute("SELECT day, topics_json FROM topic_days_v1").fetchall():
            topics.set_day(conn, day, json.loads(stored), f"{day}T00:00:00+00:00")
        for source, stored in conn.execute("SELECT source, list_json FROM model_lists_v1").fetchall():
            cached = json.loads(stored)
            conn.execute("INSERT INTO model_lists VALUES (?, ?, ?)", (source, cached["at"], json.dumps(cached["options"], ensure_ascii=False)))

    def _session(self, row: sqlite3.Row) -> None:
        conn, session_id, created_at = self.conn, row["id"], row["created_at"]
        content = json.loads(row["content_json"])
        article = ArticleDraft.model_validate(content["article"])
        note = conn.execute("SELECT text FROM notes_v1 WHERE session_id = ?", (session_id,)).fetchone()
        conn.execute(
            "INSERT INTO sessions (id, created_at, topic_id, title, note, questions, sources, translation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, created_at, topics.ensure(conn, row["topic"], Category.TYPED, created_at), row["title"], note[0] if note else "", *(
                json.dumps([m.model_dump() for m in models], ensure_ascii=False) for models in (article.questions, article.sources, article.translation)
            )),
        )
        conn.executemany(
            "INSERT INTO paragraphs (session_id, position, text) VALUES (?, ?, ?)",
            [(session_id, i, text) for i, text in enumerate(paragraphs_of(article.body))],
        )
        # v1 starred by the exact text the session showed.
        stars = {"expression": set(), "word": set()}
        for kind, item in conn.execute("SELECT kind, item FROM stars_v1 WHERE session_id = ?", (session_id,)):
            stars.setdefault(kind, set()).add(item)
        for i, raw in enumerate(content["vocabulary"]):
            word = VocabularyDraft.model_validate(raw)
            conn.execute(
                "INSERT INTO vocabulary (session_id, position, word, pos, definition, synonyms, example, korean, scene, caption,"
                " picture_id, example_picture_id, starred) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, i, word.word, word.pos, word.definition, json.dumps(word.synonyms, ensure_ascii=False), word.example,
                 word.korean, word.scene, word.caption, self._picture(raw.get("image"), created_at),
                 self._picture(raw.get("example_image"), created_at), word.word in stars["word"]),
            )
        taught: list[str] = []
        for raw in content["expressions"]:
            phrase = raw["phrase"]
            if key(phrase) in taught:
                log.warning("session %s teaches %r twice; kept once", session_id, phrase)
                continue
            expression_id = upsert_expression(
                conn, phrase, raw["meaning"], raw.get("synonyms", []), raw["examples"], raw["usage_note"], raw.get("korean"), None, "session", created_at
            )
            conn.execute(
                "INSERT INTO session_expressions (session_id, expression_id, position, starred) VALUES (?, ?, ?, ?)",
                (session_id, expression_id, len(taught), phrase in stars["expression"]),
            )
            taught.append(key(phrase))
        self.report.sessions += 1

    def _picture(self, name: str | None, created_at: str) -> int | None:
        """The pictures row for a v1 file name; None (and counted) when the file is gone."""
        if not name:
            return None
        self.referenced.add(name)
        if name in self.pictures:
            return self.pictures[name]
        if name not in self.files:
            log.warning("picture %s is not in %s; its word goes without it", name, self.images_dir)
            self.report.pictures_missing += 1
            return None
        picture_id = self.conn.execute("INSERT INTO pictures (created_at) VALUES (?)", (created_at,)).lastrowid
        if f"{picture_id}.png" in self.files:
            raise RuntimeError(f"{picture_id}.png already exists in {self.images_dir}; move it aside and start again")
        self.pictures[name] = picture_id
        return picture_id

    def _paragraph(self, session_id: int | None, text: str) -> int | None:
        """The session's paragraph with this text: exactly once trimmed, else with its whitespace evened out."""
        candidates = self.conn.execute("SELECT id, text FROM paragraphs WHERE session_id = ? ORDER BY position", (session_id,)).fetchall()
        for match in (lambda t: t.strip(), lambda t: " ".join(t.split())):
            found = next((pid for pid, ptext in candidates if match(ptext) == match(text)), None)
            if found is not None:
                return found
        return None

    def _readings(self) -> None:
        for row in self.conn.execute("SELECT * FROM readings_v1 ORDER BY id").fetchall():
            paragraph_id = self._paragraph(row["session_id"], row["paragraph"])
            if paragraph_id is None:
                log.warning("reading %s of session %s matches no paragraph, dropped: %r", row["id"], row["session_id"], row["paragraph"])
                self.report.readings_dropped += 1
                continue
            saved = row["corrections_json"]
            corrections = None if saved is None else json.dumps([c for c in json.loads(saved) if c.get("kind") != "phrasing"], ensure_ascii=False)
            self.conn.execute(
                "INSERT INTO readings (id, created_at, paragraph_id, user_text, seconds, corrections) VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["created_at"], paragraph_id, row["user_text"], row["seconds"], corrections),
            )

    def _summaries(self) -> None:
        for row in self.conn.execute("SELECT * FROM summaries_v1 ORDER BY id").fetchall():
            paragraph_id = self._paragraph(row["session_id"], row["paragraph"])
            if paragraph_id is None:
                log.warning("summary %s of session %s matches no paragraph, dropped: %r", row["id"], row["session_id"], row["paragraph"])
                self.report.summaries_dropped += 1
                continue
            self.conn.execute(
                "INSERT INTO summaries (id, created_at, paragraph_id, user_text, feedback, seconds) VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["created_at"], paragraph_id, row["user_text"], row["feedback_json"], row["seconds"]),
            )

    def _target(self, session_id: int, text: str) -> tuple[str, int] | None:
        """What a v1 example was made with: the session's expression or word with this exact text, else the
        expression of the same normalized phrase. (Words are matched exactly: their keys collide too easily.)"""
        conn = self.conn
        taught = conn.execute(
            "SELECT se.id, e.phrase, e.key FROM session_expressions se JOIN expressions e ON e.id = se.expression_id WHERE se.session_id = ?",
            (session_id,),
        ).fetchall()
        words = conn.execute("SELECT id, word FROM vocabulary WHERE session_id = ?", (session_id,)).fetchall()
        for found in (
            next((("session_expression_id", t["id"]) for t in taught if t["phrase"] == text), None),
            next((("vocabulary_id", w["id"]) for w in words if w["word"] == text), None),
            next((("session_expression_id", t["id"]) for t in taught if t["key"] == key(text)), None),
        ):
            if found:
                return found
        return None

    def _examples(self) -> None:
        for row in self.conn.execute("SELECT * FROM examples_v1 ORDER BY id").fetchall():
            target = self._target(row["session_id"], row["expression"])
            if target is None:
                log.warning("example %s of session %s names %r, which the session did not teach; dropped", row["id"], row["session_id"], row["expression"])
                self.report.examples_dropped += 1
                continue
            column, target_id = target
            self.conn.execute(
                f"INSERT INTO examples (id, created_at, {column}, user_text, coach_text, seconds) VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["created_at"], target_id, row["user_text"], row["coach_text"], row["seconds"]),
            )

    def _carry_counters(self) -> None:
        conn = self.conn
        for table in COUNTED:
            old = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (f"{table}_v1",)).fetchone()
            if old is None:
                continue
            if conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = ?", (old[0], table)).rowcount == 0:
                conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, old[0]))

    def _rename_files(self) -> None:
        assert self.images_dir is not None or not self.pictures
        for name, picture_id in self.pictures.items():
            try:
                (self.images_dir / name).rename(self.images_dir / f"{picture_id}.png")
                self.report.pictures_renamed += 1
            except OSError as e:
                log.warning("could not rename %s to %s.png: %s", name, picture_id, e)
