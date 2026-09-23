"""How long each drawn picture took and what it cost (where the provider says), per model, so the
settings modal can show what a model takes here instead of a list price, and a job can foresee
how long its pictures will take."""

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

    def record(self, model: str, seconds: float | None, cost: float | None = None) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO image_stats (created_at, model, seconds, cost) VALUES (?, ?, ?, ?)",
                (datetime.now(UTC).isoformat(), model, seconds, cost),
            )

    def stats(self) -> dict[str, PictureStat]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """SELECT model, AVG(seconds), AVG(cost) FROM (
                       SELECT model, seconds, cost, ROW_NUMBER() OVER (PARTITION BY model ORDER BY id DESC) AS n FROM image_stats
                   ) WHERE n <= ? GROUP BY model""",
                (self.RECENT,),
            ).fetchall()
        return {model: PictureStat(seconds, cost) for model, seconds, cost in rows}

    def seconds(self, model: str) -> float | None:
        return self.stats().get(model, PictureStat()).seconds
