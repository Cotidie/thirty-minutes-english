"""The one SQLite file, and a repository per group of tables on it."""

import sqlite3
from pathlib import Path

from app.db.caches import CacheRepo
from app.db.pictures import PictureRepo
from app.db.pins import PinRepo
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
CREATE TABLE IF NOT EXISTS image_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    seconds REAL,
    cost REAL
);
CREATE TABLE IF NOT EXISTS model_pins (
    source TEXT NOT NULL,
    model TEXT NOT NULL,
    pinned_at TEXT NOT NULL,
    PRIMARY KEY (source, model)
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
            _carry_over_costs(conn)
        self.sessions = SessionRepo(self)
        self.records = RecordRepo(self)
        self.caches = CacheRepo(self)
        self.pictures = PictureRepo(self)
        self.pins = PinRepo(self)
        self.settings = SettingsRepo(self)

    def connect(self) -> sqlite3.Connection:
        """A connection whose `with` block is one transaction."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn


def _carry_over_costs(conn: sqlite3.Connection) -> None:
    """Moves the costs of the table before seconds were kept into image_stats, once."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'image_costs'").fetchone():
        conn.execute("INSERT INTO image_stats (created_at, model, cost) SELECT created_at, model, cost FROM image_costs ORDER BY id")
        conn.execute("DROP TABLE image_costs")
