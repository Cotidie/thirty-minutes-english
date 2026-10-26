"""Every table STRICT, every reference a foreign key. JSON lives in TEXT columns only for values read
and written whole with their row; anything pointed at is a row of its own."""

import json
import sqlite3
from datetime import UTC, datetime

from app.db import topics
from app.models import Category

VERSION = 5

# Added in v3: images under the article's paragraphs.
FIGURES = """
CREATE TABLE figures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    picture_id   INTEGER NOT NULL REFERENCES pictures(id),
    caption      TEXT    NOT NULL,
    source_url   TEXT,
    credit       TEXT
) STRICT;

CREATE INDEX figures_paragraph ON figures (paragraph_id);
"""

# Added in v4: topics are rows; a day's news lists them, and a session points at its own.
TOPICS = """
CREATE TABLE topics (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    text     TEXT    NOT NULL UNIQUE,
    category TEXT    NOT NULL,
    added_at TEXT    NOT NULL
) STRICT;

CREATE TABLE topic_days (
    day      TEXT    NOT NULL,
    position INTEGER NOT NULL,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    PRIMARY KEY (day, position)
) STRICT;

CREATE INDEX topic_days_topic ON topic_days (topic_id);
"""

# Added in v5: the expressions swapped out of a session, which count as used there.
SWAPS = """
CREATE TABLE swapped_expressions (
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    expression_id INTEGER NOT NULL REFERENCES expressions(id) ON DELETE CASCADE,
    swapped_at    TEXT    NOT NULL,
    PRIMARY KEY (session_id, expression_id)
) STRICT;

CREATE INDEX swapped_expressions_expression ON swapped_expressions (expression_id);
"""

SESSIONS = """
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    topic_id    INTEGER NOT NULL REFERENCES topics(id),
    title       TEXT    NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',
    questions   TEXT    NOT NULL,
    sources     TEXT    NOT NULL,
    translation TEXT    NOT NULL
) STRICT;

CREATE INDEX sessions_topic ON sessions (topic_id);
"""

SCHEMA = TOPICS + SESSIONS + """

CREATE TABLE paragraphs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    UNIQUE (session_id, position)
) STRICT;

CREATE TABLE vocabulary (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position           INTEGER NOT NULL,
    word               TEXT    NOT NULL,
    pos                TEXT    NOT NULL,
    definition         TEXT    NOT NULL,
    synonyms           TEXT    NOT NULL,
    example            TEXT    NOT NULL,
    korean             TEXT,
    scene              TEXT,
    caption            TEXT,
    picture_id         INTEGER REFERENCES pictures(id),
    example_picture_id INTEGER REFERENCES pictures(id),
    starred            INTEGER NOT NULL DEFAULT 0,
    UNIQUE (session_id, position)
) STRICT;

CREATE TABLE expressions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT    NOT NULL UNIQUE,
    phrase     TEXT    NOT NULL,
    meaning    TEXT    NOT NULL,
    synonyms   TEXT    NOT NULL,
    examples   TEXT    NOT NULL,
    usage_note TEXT    NOT NULL,
    korean     TEXT,
    setting    TEXT,
    source     TEXT    NOT NULL,
    added_at   TEXT    NOT NULL
) STRICT;

CREATE TABLE session_expressions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    expression_id INTEGER NOT NULL REFERENCES expressions(id),
    position      INTEGER NOT NULL,
    starred       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (session_id, expression_id),
    UNIQUE (session_id, position)
) STRICT;

CREATE TABLE pictures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model      TEXT,
    seconds    REAL,
    cost       REAL
) STRICT;

CREATE TABLE examples (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at            TEXT    NOT NULL,
    session_expression_id INTEGER REFERENCES session_expressions(id) ON DELETE CASCADE,
    vocabulary_id         INTEGER REFERENCES vocabulary(id) ON DELETE CASCADE,
    user_text             TEXT    NOT NULL,
    coach_text            TEXT    NOT NULL,
    seconds               REAL    NOT NULL DEFAULT 0,
    CHECK ((session_expression_id IS NULL) <> (vocabulary_id IS NULL))
) STRICT;

CREATE TABLE readings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    user_text    TEXT    NOT NULL,
    seconds      REAL    NOT NULL DEFAULT 0,
    corrections  TEXT
) STRICT;

CREATE TABLE summaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    user_text    TEXT    NOT NULL,
    feedback     TEXT    NOT NULL,
    seconds      REAL    NOT NULL DEFAULT 0
) STRICT;

CREATE TABLE settings    (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE model_pins  (source TEXT NOT NULL, model TEXT NOT NULL, pinned_at TEXT NOT NULL, PRIMARY KEY (source, model)) STRICT;
CREATE TABLE model_lists (source TEXT PRIMARY KEY, fetched_at REAL NOT NULL, options TEXT NOT NULL) STRICT;
CREATE TABLE stage_times (id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL, seconds REAL NOT NULL, finished_at TEXT NOT NULL) STRICT;

CREATE INDEX paragraphs_session ON paragraphs (session_id);
CREATE INDEX vocabulary_session ON vocabulary (session_id);
CREATE INDEX session_expressions_session ON session_expressions (session_id);
CREATE INDEX session_expressions_expression ON session_expressions (expression_id);
CREATE INDEX examples_session_expression ON examples (session_expression_id);
CREATE INDEX examples_vocabulary ON examples (vocabulary_id);
CREATE INDEX readings_paragraph ON readings (paragraph_id);
CREATE INDEX summaries_paragraph ON summaries (paragraph_id);
CREATE INDEX stage_times_stage ON stage_times (stage, id);
""" + FIGURES + SWAPS


def _run(conn: sqlite3.Connection, script: str) -> None:
    """One statement at a time, so it can run inside a caller's transaction (executescript would commit it)."""
    for statement in script.split(";"):
        if statement.strip():
            conn.execute(statement)


def create(conn: sqlite3.Connection) -> None:
    """Every current table on an empty file, with the curated topics."""
    _run(conn, SCHEMA)
    topics.seed(conn, _now())
    conn.execute(f"PRAGMA user_version = {VERSION}")


def upgrade(conn: sqlite3.Connection, version: int) -> None:
    """An older file brought to the current version, a step at a time, each in its own transaction."""
    if version < 3:
        _run(conn, FIGURES)
        conn.execute("PRAGMA user_version = 3")
    if version < 4:
        _topics(conn)
    if version < 5:
        _run(conn, SWAPS)
        conn.execute("PRAGMA user_version = 5")


def _topics(conn: sqlite3.Connection) -> None:
    """v3 to v4: the topics table, seeded; the day lists and the session topics turned into references.
    Rebuilding sessions drops the old table, which with foreign keys on would delete every session's
    children, so this runs with them off and checks them before it commits."""
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute("ALTER TABLE topic_days RENAME TO topic_days_v3")
        _run(conn, TOPICS)
        topics.seed(conn, _now())
        for day, texts in conn.execute("SELECT day, topics FROM topic_days_v3 ORDER BY day").fetchall():
            topics.set_day(conn, day, json.loads(texts), f"{day}T00:00:00+00:00")
        conn.execute("DROP TABLE topic_days_v3")
        counter = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'sessions'").fetchone()
        conn.execute(SESSIONS.split(";")[0].replace("CREATE TABLE sessions", "CREATE TABLE sessions_v4"))
        for row in conn.execute("SELECT * FROM sessions ORDER BY id").fetchall():
            session_id, created_at, topic, *rest = tuple(row)
            topic_id = topics.ensure(conn, topic, Category.TYPED, created_at)
            conn.execute("INSERT INTO sessions_v4 VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (session_id, created_at, topic_id, *rest))
        conn.execute("DROP TABLE sessions")
        conn.execute("ALTER TABLE sessions_v4 RENAME TO sessions")
        conn.execute(SESSIONS.split(";")[1])
        if counter:  # deleted sessions keep their ids retired
            conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'sessions'", (counter[0],))
        if broken := conn.execute("PRAGMA foreign_key_check").fetchall():
            raise sqlite3.IntegrityError(f"foreign keys broken by the v4 upgrade: {broken[:5]}")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _now() -> str:
    return datetime.now(UTC).isoformat()
