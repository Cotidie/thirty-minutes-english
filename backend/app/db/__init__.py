"""The one SQLite file, and a repository per group of tables on it."""

import logging
import sqlite3
from pathlib import Path

from app.db import migrate, schema
from app.db.accounts import AccountRepo
from app.db.caches import CacheRepo
from app.db.expressions import ExpressionRepo
from app.db.pictures import PictureRepo
from app.db.pins import PinRepo
from app.db.records import RecordRepo
from app.db.sessions import SessionRepo
from app.db.settings import SettingsRepo
from app.db.shares import ShareRepo
from app.db.stages import StageRepo
from app.db.topics import TopicRepo
from app.live.changes import Changes

log = logging.getLogger(__name__)


class Database:
    def __init__(self, path: Path | str, images_dir: Path | str | None = None) -> None:
        """`images_dir` holds the picture files; next to the file by default."""
        self.path = Path(path)
        self.images_dir = Path(images_dir) if images_dir is not None else self.path.parent / "images"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            if migrate.is_v1(conn):
                saved = migrate.backup(self.path, 1)
                renames = saved.with_name(f"{saved.name}.renames.json")
                report = migrate.migrate_v1(conn, self.images_dir, renames)
                log.info("migrated %s to schema v2 (v1 copy: %s, file renames: %s): %s", self.path, saved.name, renames.name, report)
            elif (version := conn.execute("PRAGMA user_version").fetchone()[0]) == 0:
                schema.create(conn)
            elif version < schema.VERSION:
                saved = migrate.backup(self.path, version)
                schema.upgrade(conn, version)
                log.info("upgraded %s from schema v%d to v%d (copy: %s)", self.path, version, schema.VERSION, saved.name)
        self.changes = Changes()
        self.account_changes = Changes()
        self.sessions = SessionRepo(self)
        self.expressions = ExpressionRepo(self)
        self.records = RecordRepo(self)
        self.caches = CacheRepo(self)
        self.pictures = PictureRepo(self)
        self.stages = StageRepo(self)
        self.pins = PinRepo(self)
        self.settings = SettingsRepo(self)
        self.topics = TopicRepo(self)
        self.accounts = AccountRepo(self)
        self.shares = ShareRepo(self)

    def connect(self) -> sqlite3.Connection:
        """A connection whose `with` block is one transaction, with foreign keys enforced."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
