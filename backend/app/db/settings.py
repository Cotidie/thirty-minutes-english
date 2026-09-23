"""What the user saved in the settings modal."""

from collections.abc import Mapping
from typing import TYPE_CHECKING

from app.config.settings import validate

if TYPE_CHECKING:
    from app.db import Database


class SettingsRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def load(self) -> dict[str, str]:
        with self._db.connect() as conn:
            return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}

    def save(self, values: Mapping[str, str]) -> None:
        """Raises InvalidSetting, and saves nothing, when any value is off."""
        validate(values)
        with self._db.connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", values.items())
