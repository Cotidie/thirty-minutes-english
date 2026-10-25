"""How long each generation stage took on finished runs, so the next run's estimate survives a restart."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.generation.progress import Stage

if TYPE_CHECKING:
    from app.db import Database


class StageRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def add(self, stage: Stage, seconds: float) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO stage_times (stage, seconds, finished_at) VALUES (?, ?, ?)",
                (stage.value, seconds, datetime.now(UTC).isoformat()),
            )

    def recent(self, stage: Stage, n: int = 5) -> list[float]:
        """The latest `n` times of `stage`, oldest first."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT seconds FROM stage_times WHERE stage = ? ORDER BY id DESC LIMIT ?", (stage.value, n)
            ).fetchall()
        return [seconds for (seconds,) in reversed(rows)]
