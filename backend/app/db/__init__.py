"""The one SQLite file, and a repository per group of tables on it."""

import sqlite3
from pathlib import Path

from app.db.caches import CacheRepo
from app.db.costs import CostRepo
from app.db.records import RecordRepo
from app.db.sessions import SessionRepo
from app.db.settings import SettingsRepo

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    content_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stars (
    session_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    item TEXT NOT NULL,
    PRIMARY KEY (session_id, kind, item)
);
CREATE TABLE IF NOT EXISTS asks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id INTEGER,
    user_text TEXT NOT NULL,
    coach_text TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0,
    card_json TEXT
);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id INTEGER,
    paragraph TEXT NOT NULL,
    user_text TEXT NOT NULL,
    coach_text TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0,
    corrections_json TEXT
);
CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id INTEGER NOT NULL,
    expression TEXT NOT NULL,
    user_text TEXT NOT NULL,
    coach_text TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS topic_days (
    day TEXT PRIMARY KEY,
    topics_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS phrasings (
    paragraph TEXT PRIMARY KEY,
    breaks_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS image_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    cost REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS model_lists (
    source TEXT PRIMARY KEY,
    list_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
        self.sessions = SessionRepo(self)
        self.records = RecordRepo(self)
        self.caches = CacheRepo(self)
        self.costs = CostRepo(self)
        self.settings = SettingsRepo(self)

    def connect(self) -> sqlite3.Connection:
        """A connection whose `with` block is one transaction."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn
