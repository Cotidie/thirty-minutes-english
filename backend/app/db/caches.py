"""Answers worth keeping so the model runs once: a day's news topics and the providers' model lists."""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database


@dataclass(frozen=True)
class ModelList:
    """A provider's model list and when it was fetched (unix seconds)."""

    fetched_at: float
    options: list[dict]


class CacheRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def get_daily_topics(self, day: str) -> list[str] | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT topics FROM topic_days WHERE day = ?", (day,)).fetchone()
        return json.loads(row["topics"]) if row else None

    def set_daily_topics(self, day: str, topics: list[str]) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO topic_days (day, topics) VALUES (?, ?) ON CONFLICT (day) DO UPDATE SET topics = excluded.topics",
                (day, json.dumps(topics, ensure_ascii=False)),
            )

    def get_model_list(self, source: str) -> ModelList | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT fetched_at, options FROM model_lists WHERE source = ?", (source,)).fetchone()
        return ModelList(row["fetched_at"], json.loads(row["options"])) if row else None

    def set_model_list(self, source: str, fetched_at: float, options: list[dict]) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO model_lists (source, fetched_at, options) VALUES (?, ?, ?)"
                " ON CONFLICT (source) DO UPDATE SET fetched_at = excluded.fetched_at, options = excluded.options",
                (source, fetched_at, json.dumps(options, ensure_ascii=False)),
            )
