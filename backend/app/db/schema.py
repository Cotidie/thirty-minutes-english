"""Schema v2: every table STRICT, every reference a foreign key. JSON lives in TEXT columns only
for values read and written whole with their row; anything pointed at is a row of its own."""

import sqlite3

VERSION = 2

SCHEMA = """
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    topic       TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',
    questions   TEXT    NOT NULL,
    sources     TEXT    NOT NULL,
    translation TEXT    NOT NULL
) STRICT;

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
CREATE TABLE topic_days  (day TEXT PRIMARY KEY, topics TEXT NOT NULL) STRICT;
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
"""


def create(conn: sqlite3.Connection) -> None:
    """The v2 tables on an empty file."""
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {VERSION}")
