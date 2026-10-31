"""What each account gained and spent. The balance is the sum of its rows; the admin spends without any."""

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.credits import PRICES
from app.live.changes import AccountChange
from app.models import CreditEntry, User

if TYPE_CHECKING:
    from app.db import Database


class CreditRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def balance(self, user_id: int) -> int:
        with self._db.connect() as conn:
            return _balance(conn, user_id)

    def recent(self, user_id: int, limit: int = 10) -> list[CreditEntry]:
        """The newest first."""
        with self._db.connect() as conn:
            rows = conn.execute("SELECT at, amount, kind, detail FROM credits WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
        return [CreditEntry(at=row["at"], amount=row["amount"], kind=row["kind"], detail=row["detail"]) for row in rows]

    def grant(self, user_id: int, amount: int, by: int) -> None:
        """Added by the admin, or taken back when `amount` is negative, which may leave the balance below zero."""
        with self._db.connect() as conn:
            _add_row(conn, user_id, amount, "grant", None, by)
        self._db.account_changes.publish(user_id, AccountChange.CREDITS)

    def charge(self, user: User, kind: str, detail: str | None = None) -> bool:
        """Takes the price of `kind`, or nothing when the balance cannot cover it. The write lock comes first,
        so two charges at once cannot both spend the same credits."""
        if user.is_admin:
            return True
        price = PRICES[kind]
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if _balance(conn, user.id) < price:
                return False
            _add_row(conn, user.id, -price, kind, detail, None)
        self._db.account_changes.publish(user.id, AccountChange.CREDITS)
        return True

    def refund(self, user_id: int, amount: int, detail: str | None) -> None:
        with self._db.connect() as conn:
            _add_row(conn, user_id, amount, "refund", detail, None)
        self._db.account_changes.publish(user_id, AccountChange.CREDITS)


def _balance(conn: sqlite3.Connection, user_id: int) -> int:
    return conn.execute("SELECT COALESCE(SUM(amount), 0) FROM credits WHERE user_id = ?", (user_id,)).fetchone()[0]


def _add_row(conn: sqlite3.Connection, user_id: int, amount: int, kind: str, detail: str | None, granted_by: int | None) -> None:
    conn.execute(
        "INSERT INTO credits (user_id, at, amount, kind, detail, granted_by) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, datetime.now(UTC).isoformat(), amount, kind, detail, granted_by),
    )
