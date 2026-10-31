"""Every table STRICT, every reference a foreign key. JSON lives in TEXT columns only for values read
and written whole with their row; anything pointed at is a row of its own."""

import json
import sqlite3
from datetime import UTC, datetime

from app.db import topics
from app.models import Category

VERSION = 11

# Added in v3, by session since v9: images under the article's paragraphs, and its cover (no paragraph) under the title.
FIGURES = """
CREATE TABLE figures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    paragraph_id INTEGER REFERENCES paragraphs(id) ON DELETE CASCADE,
    picture_id   INTEGER NOT NULL REFERENCES pictures(id),
    caption      TEXT    NOT NULL,
    source_url   TEXT,
    credit       TEXT
) STRICT;

CREATE INDEX figures_session ON figures (session_id);
CREATE UNIQUE INDEX figures_cover ON figures (session_id) WHERE paragraph_id IS NULL;
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

# Added in v6: a Korean sentence the pair say in English with the expression, and the English model
# answer, as one JSON object {"korean", "english"}; NULL until the corpus has one.
KOREAN_EXAMPLES = """
ALTER TABLE expressions ADD COLUMN korean_example TEXT;
"""

# Rebuilt in v7: sentences are made with words only, since expressions lost their Your turn.
EXAMPLES = """
CREATE TABLE examples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary(id) ON DELETE CASCADE,
    user_text     TEXT    NOT NULL,
    coach_text    TEXT    NOT NULL,
    seconds       REAL    NOT NULL DEFAULT 0
) STRICT;

CREATE INDEX examples_vocabulary ON examples (vocabulary_id);
"""

# v8: OpenAI and Comfy are gone. Their keys, the voice provider switch, their pins and their cached model
# lists leave; a voice model saved while OpenAI was the provider, and a Comfy image choice, fall back to
# the defaults. A file that never chose Gemini was on OpenAI, the old default.
RETIRED_PROVIDERS = """
DELETE FROM settings WHERE key = 'VOICE_MODEL'
    AND NOT EXISTS (SELECT 1 FROM settings WHERE key = 'VOICE_PROVIDER' AND value = 'gemini');
DELETE FROM settings WHERE key IN ('IMAGE_PROVIDER', 'IMAGE_MODEL')
    AND EXISTS (SELECT 1 FROM settings WHERE key = 'IMAGE_PROVIDER' AND value = 'comfy');
DELETE FROM settings WHERE key IN ('OPENAI_API_KEY', 'COMFY_API_KEY', 'VOICE_PROVIDER');
DELETE FROM model_pins WHERE source IN ('comfy_images', 'openai_voice', 'openai_text');
DELETE FROM model_lists WHERE source IN ('comfy_images', 'openai_voice', 'openai_text');
"""

# Added in v10: accounts, their logins, whom a session is shared with, and who made each session.
ACCOUNTS = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    can_create    INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE UNIQUE INDEX users_one_admin ON users (is_admin) WHERE is_admin = 1;

CREATE TABLE logins (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT    NOT NULL
) STRICT;

CREATE INDEX logins_user ON logins (user_id);

CREATE TABLE session_shares (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    PRIMARY KEY (session_id, user_id)
) STRICT;

CREATE INDEX session_shares_user ON session_shares (user_id);

ALTER TABLE sessions ADD COLUMN created_by INTEGER REFERENCES users(id);
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
CREATE INDEX readings_paragraph ON readings (paragraph_id);
CREATE INDEX summaries_paragraph ON summaries (paragraph_id);
CREATE INDEX stage_times_stage ON stage_times (stage, id);
""" + FIGURES + SWAPS + KOREAN_EXAMPLES + EXAMPLES + ACCOUNTS


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
    if version < 6:
        _run(conn, KOREAN_EXAMPLES)
        conn.execute("PRAGMA user_version = 6")
    if version < 7:
        _examples_of_words(conn)
    if version < 8:
        _run(conn, RETIRED_PROVIDERS)
        conn.execute("PRAGMA user_version = 8")
    if version < 9:
        _figures_by_session(conn)
    if version < 10:
        _run(conn, ACCOUNTS)
        conn.execute("PRAGMA user_version = 10")
    if version < 11:
        _economics_topics(conn)


def _economics_topics(conn: sqlite3.Connection) -> None:
    """v10 to v11: the new pool and nothing else, so a curated topic someone deleted stays deleted."""
    topics.seed_pool(conn, Category.ECONOMICS, _now())
    conn.execute("PRAGMA user_version = 11")


def _figures_by_session(conn: sqlite3.Connection) -> None:
    """v8 to v9: each figure points at its session, so one with no paragraph can be the article's cover."""
    conn.execute("ALTER TABLE figures RENAME TO figures_v8")
    for index in ("figures_paragraph", "figures_session", "figures_cover"):
        conn.execute(f"DROP INDEX IF EXISTS {index}")
    _run(conn, FIGURES)
    conn.execute(
        "INSERT INTO figures (id, session_id, paragraph_id, picture_id, caption, source_url, credit)"
        " SELECT f.id, p.session_id, f.paragraph_id, f.picture_id, f.caption, f.source_url, f.credit"
        " FROM figures_v8 f JOIN paragraphs p ON p.id = f.paragraph_id"
    )
    conn.execute("DROP TABLE figures_v8")
    conn.execute("PRAGMA user_version = 9")


def _examples_of_words(conn: sqlite3.Connection) -> None:
    """v6 to v7: the examples table without its expression column; sentences made with an expression go,
    and the id counter carries on so a new sentence never takes a gone one's id."""
    (counter,) = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM sqlite_sequence WHERE name = 'examples'").fetchone()
    conn.execute("ALTER TABLE examples RENAME TO examples_v6")
    conn.execute("DROP INDEX IF EXISTS examples_session_expression")
    conn.execute("DROP INDEX IF EXISTS examples_vocabulary")
    _run(conn, EXAMPLES)
    conn.execute(
        "INSERT INTO examples (id, created_at, vocabulary_id, user_text, coach_text, seconds)"
        " SELECT id, created_at, vocabulary_id, user_text, coach_text, seconds FROM examples_v6 WHERE vocabulary_id IS NOT NULL"
    )
    conn.execute("DROP TABLE examples_v6")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('examples', 'examples_v6')")
    conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('examples', ?)", (counter,))
    conn.execute("PRAGMA user_version = 7")


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
