"""Every picture drawn, one row each: its file is images/{id}.png. How long a model took and what it
cost (where the provider says) feed the settings modal and a job's estimate of its pictures."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database


@dataclass(frozen=True)
class PictureStat:
    """Averages over a model's latest pictures; None where nothing was measured."""

    seconds: float | None = None
    cost: float | None = None


class PictureRepo:
    RECENT = 20  # the averages cover each model's latest pictures

    def __init__(self, db: "Database") -> None:
        self._db = db

    def add(self, model: str | None, seconds: float | None, cost: float | None) -> int:
        """The new picture's id, which names its file. `model` is None for pictures carried over from v1."""
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO pictures (created_at, model, seconds, cost) VALUES (?, ?, ?, ?)",
                (datetime.now(UTC).isoformat(), model, seconds, cost),
            )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def stats(self) -> dict[str, PictureStat]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """SELECT model, AVG(seconds), AVG(cost) FROM (
                       SELECT model, seconds, cost, ROW_NUMBER() OVER (PARTITION BY model ORDER BY id DESC) AS n
                       FROM pictures WHERE model IS NOT NULL
                   ) WHERE n <= ? GROUP BY model""",
                (self.RECENT,),
            ).fetchall()
        return {model: PictureStat(seconds, cost) for model, seconds, cost in rows}

    def seconds(self, model: str) -> float | None:
        return self.stats().get(model, PictureStat()).seconds
