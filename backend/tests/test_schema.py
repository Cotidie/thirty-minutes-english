import sqlite3

import pytest

from app.db import Database, schema
from app.db.pictures import PictureStat
from app.generation.progress import Stage
from app.models import Category
from tests.conftest import CURATED_TOPICS, sample_draft


def as_v3(path) -> None:
    """Rewrites a current file the way v3 kept topics: the text on each session, a JSON list per day, no topics table."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = OFF")
    with conn:
        days = conn.execute(
            """SELECT day, json_group_array(text) FROM (SELECT d.day, t.text FROM topic_days d JOIN topics t ON t.id = d.topic_id
               ORDER BY d.day, d.position) GROUP BY day"""
        ).fetchall()
        conn.execute(
            """CREATE TABLE sessions_v3 (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, topic TEXT NOT NULL,
               title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', questions TEXT NOT NULL, sources TEXT NOT NULL,
               translation TEXT NOT NULL) STRICT"""
        )
        conn.execute(
            """INSERT INTO sessions_v3 SELECT s.id, s.created_at, t.text, s.title, s.note, s.questions, s.sources, s.translation
               FROM sessions s JOIN topics t ON t.id = s.topic_id"""
        )
        counter = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'sessions'").fetchone()[0]
        conn.execute("DROP TABLE sessions")
        conn.execute("ALTER TABLE sessions_v3 RENAME TO sessions")
        conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'sessions'", (counter,))
        conn.execute("DROP TABLE topic_days")
        conn.execute("DROP TABLE topics")
        conn.execute("CREATE TABLE topic_days (day TEXT PRIMARY KEY, topics TEXT NOT NULL) STRICT")
        conn.executemany("INSERT INTO topic_days VALUES (?, ?)", days)
        conn.execute("DROP TABLE swapped_expressions")
        conn.execute("PRAGMA user_version = 3")
    conn.close()


def test_a_fresh_file_is_at_the_current_version_with_strict_tables_and_live_foreign_keys(tmp_path):
    db = Database(tmp_path / "s.db")
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == schema.VERSION
        sqls = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        assert sqls and all(s.rstrip().endswith("STRICT") for s in sqls)
        assert {r[1] for r in conn.execute("PRAGMA table_info(sessions)")} == {"id", "created_at", "topic_id", "title", "note", "questions", "sources", "translation"}
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO paragraphs (session_id, position, text) VALUES (999, 0, 'x')")


def test_stage_times_keep_the_latest_runs_oldest_first(tmp_path):
    stages = Database(tmp_path / "s.db").stages
    for s in (10, 20, 30, 40, 50, 60):
        stages.add(Stage.WRITING, s)
    assert stages.recent(Stage.WRITING, 5) == [20, 30, 40, 50, 60]
    assert stages.recent(Stage.SEARCHING) == []


def test_pictures_are_rows_with_an_id_and_stats_skip_unknown_models(tmp_path):
    pictures = Database(tmp_path / "s.db").pictures
    first = pictures.add("m", 4.0, 0.01)
    assert pictures.add("m", 6.0, None) == first + 1
    pictures.add(None, 9.0, None)
    assert pictures.stats() == {"m": PictureStat(5.0, 0.01)}
    assert pictures.seconds("m") == 5.0 and pictures.seconds("none") is None


def test_a_v2_file_gains_the_figures_table_and_keeps_its_sessions(tmp_path):
    path = tmp_path / "s.db"
    session = Database(path).sessions.create(sample_draft(), [])
    as_v3(path)
    with sqlite3.connect(path) as conn:  # and on back to how a v2 file looked
        conn.execute("DROP TABLE figures")
        conn.execute("PRAGMA user_version = 2")
    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == schema.VERSION
        assert conn.execute("SELECT sql FROM sqlite_master WHERE name = 'figures'").fetchone()[0].rstrip().endswith("STRICT")
    assert db.sessions.get(session.id).content.article.figures == []


def test_a_v3_file_moves_its_topics_into_rows_and_keeps_everything_else(tmp_path):
    path = tmp_path / "s.db"
    db = Database(path)
    db.topics.set_news("2026-10-25", ["News A", "News B"])
    typed = db.sessions.create(sample_draft(topic="My own topic"), [])
    curated = db.sessions.create(sample_draft(topic=CURATED_TOPICS[0].text), [])
    db.sessions.delete(db.sessions.create(sample_draft(), []).id)  # its id stays retired
    as_v3(path)

    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == schema.VERSION
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert list(tmp_path.glob("s.db.bak-v3-????-??-??"))
    assert db.topics.news("2026-10-25") == ["News A", "News B"]
    assert [(s.id, s.topic) for s in db.sessions.list_all()] == [(curated.id, CURATED_TOPICS[0].text), (typed.id, "My own topic")]
    assert db.sessions.get(typed.id).content.article.paragraphs == typed.content.article.paragraphs
    entries = {t.text: t for t in db.topics.list_all()}
    assert (entries["My own topic"].category, entries["My own topic"].sessions) == (Category.TYPED, [typed.id])
    assert (entries[CURATED_TOPICS[0].text].category, entries[CURATED_TOPICS[0].text].sessions) == (CURATED_TOPICS[0].category, [curated.id])
    assert entries["News A"].news_days == ["2026-10-25"]
    assert len(db.topics.curated()) == len(CURATED_TOPICS)
    assert db.sessions.create(sample_draft(), []).id == curated.id + 2


def test_a_v4_file_gains_the_swapped_expressions_table_and_keeps_its_sessions(tmp_path):
    path = tmp_path / "s.db"
    session = Database(path).sessions.create(sample_draft(), [])
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE swapped_expressions")
        conn.execute("PRAGMA user_version = 4")
    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert conn.execute("SELECT sql FROM sqlite_master WHERE name = 'swapped_expressions'").fetchone()[0].rstrip().endswith("STRICT")
    assert list(tmp_path.glob("s.db.bak-v4-????-??-??"))
    assert db.sessions.get(session.id).content.article.title == session.content.article.title
