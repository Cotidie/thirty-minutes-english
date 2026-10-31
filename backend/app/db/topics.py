"""The topics: the curated ones, the news Claude finds each day, and the ones typed in for a session.
Each text is kept once; topic_days lists a day's news by reference, and every session points at its topic."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models import UNCURATED, Category, Topic, TopicEntry
from app.topics.curated import CURATED

if TYPE_CHECKING:
    from app.db import Database


class TopicInUse(Exception):
    """A session points at the topic, so it stays."""


def ensure(conn: sqlite3.Connection, text: str, category: Category, added_at: str) -> int:
    """The id of the topic `text`, added under `category` when it is new; a known topic keeps its category."""
    conn.execute(
        "INSERT INTO topics (text, category, added_at) VALUES (?, ?, ?) ON CONFLICT (text) DO NOTHING", (text, category, added_at)
    )
    return conn.execute("SELECT id FROM topics WHERE text = ?", (text,)).fetchone()[0]


def set_day(conn: sqlite3.Connection, day: str, texts: list[str], added_at: str) -> None:
    """The day's news, in order, in place of what the day had."""
    ids = [ensure(conn, text, Category.NEWS, added_at) for text in texts]
    conn.execute("DELETE FROM topic_days WHERE day = ?", (day,))
    conn.executemany("INSERT INTO topic_days (day, position, topic_id) VALUES (?, ?, ?)", [(day, i, t) for i, t in enumerate(ids)])


def seed(conn: sqlite3.Connection, added_at: str) -> None:
    """The curated topics a new (or newly upgraded) file starts with."""
    for category in CURATED:
        seed_pool(conn, category, added_at)


def seed_pool(conn: sqlite3.Connection, category: Category, added_at: str) -> None:
    for text in CURATED[category]:
        ensure(conn, text, category, added_at)


class TopicRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def curated(self) -> list[Topic]:
        """The topics the pool deals from, in the order they were added."""
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT text, category FROM topics WHERE category NOT IN ({','.join('?' * len(UNCURATED))}) ORDER BY id", UNCURATED
            ).fetchall()
        return [Topic(text=r["text"], category=Category(r["category"])) for r in rows]

    def news(self, day: str) -> list[str] | None:
        """The day's news topics in order; None when none were kept for the day."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT t.text FROM topic_days d JOIN topics t ON t.id = d.topic_id WHERE d.day = ? ORDER BY d.position", (day,)
            ).fetchall()
        return [r["text"] for r in rows] or None

    def set_news(self, day: str, texts: list[str]) -> None:
        with self._db.connect() as conn:
            set_day(conn, day, texts, datetime.now(UTC).isoformat())

    def delete(self, topic_id: int) -> bool:
        """Takes the topic out of the pool and off the days that listed it; False when there was no such topic.
        Raises TopicInUse when a session points at it."""
        with self._db.connect() as conn:
            if conn.execute("SELECT 1 FROM sessions WHERE topic_id = ?", (topic_id,)).fetchone():
                raise TopicInUse(topic_id)
            conn.execute("DELETE FROM topic_days WHERE topic_id = ?", (topic_id,))
            return conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,)).rowcount > 0

    def list_all(self) -> list[TopicEntry]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """SELECT t.id, t.text, t.category, t.added_at,
                       (SELECT json_group_array(day) FROM (SELECT day FROM topic_days WHERE topic_id = t.id ORDER BY day)) AS news_days,
                       (SELECT json_group_array(id) FROM (SELECT id FROM sessions WHERE topic_id = t.id ORDER BY id)) AS sessions
                   FROM topics t ORDER BY t.id"""
            ).fetchall()
        return [
            TopicEntry(id=r["id"], text=r["text"], category=Category(r["category"]), added_at=r["added_at"],
                       news_days=json.loads(r["news_days"]), sessions=json.loads(r["sessions"]))
            for r in rows
        ]
