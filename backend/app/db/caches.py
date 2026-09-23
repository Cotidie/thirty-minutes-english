"""Answers worth keeping so the model runs once: a day's news topics, a paragraph's phrasing,
and the providers' model lists."""

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database


class CacheRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def _get(self, table: str, key_column: str, value_column: str, key: str):
        with self._db.connect() as conn:
            row = conn.execute(f"SELECT {value_column} FROM {table} WHERE {key_column} = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _set(self, table: str, key_column: str, value_column: str, key: str, value) -> None:
        with self._db.connect() as conn:
            conn.execute(
                f"INSERT INTO {table} ({key_column}, {value_column}) VALUES (?, ?)"
                f" ON CONFLICT({key_column}) DO UPDATE SET {value_column} = excluded.{value_column}",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def get_daily_topics(self, day: str) -> list[str] | None:
        return self._get("topic_days", "day", "topics_json", day)

    def set_daily_topics(self, day: str, topics: list[str]) -> None:
        self._set("topic_days", "day", "topics_json", day, topics)

    def get_phrasing(self, paragraph: str) -> list[int] | None:
        return self._get("phrasings", "paragraph", "breaks_json", paragraph)

    def set_phrasing(self, paragraph: str, breaks: list[int]) -> None:
        self._set("phrasings", "paragraph", "breaks_json", paragraph, breaks)

    def get_model_list(self, source: str) -> dict | None:
        return self._get("model_lists", "source", "list_json", source)

    def set_model_list(self, source: str, value: dict) -> None:
        self._set("model_lists", "source", "list_json", source, value)
