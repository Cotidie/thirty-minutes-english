"""What each drawn picture cost, as the image provider reported it, so the settings
modal can show what a model costs here, per picture, instead of a list price."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database


class CostRepo:
    RECENT = 20  # the average covers each model's latest pictures

    def __init__(self, db: "Database") -> None:
        self._db = db

    def record(self, model: str, cost: float) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO image_costs (created_at, model, cost) VALUES (?, ?, ?)",
                (datetime.now(UTC).isoformat(), model, cost),
            )

    def per_picture(self) -> dict[str, float]:
        """Model -> average cost of its latest pictures."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """SELECT model, AVG(cost) FROM (
                       SELECT model, cost, ROW_NUMBER() OVER (PARTITION BY model ORDER BY id DESC) AS n FROM image_costs
                   ) WHERE n <= ? GROUP BY model""",
                (self.RECENT,),
            ).fetchall()
        return dict(rows)
