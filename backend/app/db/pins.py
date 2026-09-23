"""Models the user pinned on a model list, so they stay on the menu however many newer ones come out."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database


class PinRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def pinned(self, source: str) -> list[str]:
        """The pinned models of a list (app.config.catalog source), oldest pin first."""
        with self._db.connect() as conn:
            rows = conn.execute("SELECT model FROM model_pins WHERE source = ? ORDER BY pinned_at", (source,)).fetchall()
        return [model for (model,) in rows]

    def set(self, source: str, model: str, pinned: bool) -> None:
        with self._db.connect() as conn:
            if pinned:
                conn.execute(
                    "INSERT OR IGNORE INTO model_pins (source, model, pinned_at) VALUES (?, ?, ?)",
                    (source, model, datetime.now(UTC).isoformat()),
                )
            else:
                conn.execute("DELETE FROM model_pins WHERE source = ? AND model = ?", (source, model))
