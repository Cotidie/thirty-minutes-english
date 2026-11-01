"""What each account gained and spent. The balance is the sum of its rows that count; the admin spends without any."""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.credits import PRICES
from app.live.changes import AccountChange
from app.models import CreditEntry, User

if TYPE_CHECKING:
    from app.db import Database

# Which rows count, as of the time given: a settled one, and a held one whose work may still be going on.
COUNTS = "(state = 'settled' OR (state = 'held' AND (open_until IS NULL OR open_until > ?)))"


class NotEnoughCredits(Exception):
    def __init__(self, need: int, have: int) -> None:
        super().__init__(f"this needs {need} and there are {have}")
        self.need = need
        self.have = have


class CreditRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def balance(self, user_id: int) -> int:
        with self._db.connect() as conn:
            return _balance(conn, user_id)

    def recent(self, user_id: int, limit: int = 10) -> list[CreditEntry]:
        """The newest first."""
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT at, amount, kind, detail FROM credits WHERE user_id = ? AND {COUNTS} ORDER BY id DESC LIMIT ?",
                (user_id, _now(), limit),
            ).fetchall()
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

    def hold(self, user: User, kind: str, detail: str | None = None) -> int | None:
        """Takes the price of `kind` off the balance while its work runs, or raises NotEnoughCredits; None for the
        admin, who pays nothing. The write lock comes first, so two holds at once cannot spend the same credits."""
        if user.is_admin:
            return None
        price = PRICES[kind]
        with self._db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            balance = _balance(conn, user.id)
            if balance < price:
                raise NotEnoughCredits(price, balance)
            hold = _add_row(conn, user.id, -price, kind, detail, None, state="held")
        self._db.account_changes.publish(user.id, AccountChange.CREDITS)
        return hold

    def settle(self, hold: int | None, as_kind: str | None = None) -> None:
        """The work is over and the price stays: at the price of `as_kind`, under that name, when that is what it came to."""
        if hold is None:
            return
        if as_kind is None:
            self._change("UPDATE credits SET state = 'settled' WHERE id = ? AND state = 'held' RETURNING user_id", hold)
            return
        self._tell(
            self._change(
                "UPDATE credits SET state = 'settled', kind = ?, amount = ? WHERE id = ? AND state = 'held' RETURNING user_id",
                as_kind,
                -PRICES[as_kind],
                hold,
            )
        )

    def release(self, hold: int | None) -> None:
        """The work did not get done: the price comes back and the row stays out of sight, its number never used again."""
        if hold is None:
            return
        self._tell(self._change("UPDATE credits SET state = 'released' WHERE id = ? AND state = 'held' RETURNING user_id", hold))

    def await_browser(self, hold: int | None, window: timedelta) -> None:
        """The browser takes it from here; a hold it says nothing about by then stops counting."""
        if hold is None:
            return
        self._change("UPDATE credits SET open_until = ? WHERE id = ? AND state = 'held' RETURNING user_id", _after(window), hold)

    def confirm(self, hold: int, user_id: int, window: timedelta) -> bool:
        """The browser's round connected: the price stays, though for `window` it may still report the round dropped."""
        changed = self._change(
            "UPDATE credits SET state = 'settled', open_until = ? WHERE id = ? AND user_id = ? AND state = 'held' AND open_until > ? RETURNING user_id",
            _after(window),
            hold,
            user_id,
            _now(),
        )
        return changed is not None

    def give_back(self, hold: int, user_id: int) -> bool:
        """The browser's round did not deliver. Only while `open_until` runs, so never for what the server is working on."""
        changed = self._change(
            "UPDATE credits SET state = 'released' WHERE id = ? AND user_id = ? AND state IN ('held', 'settled') AND open_until > ? RETURNING user_id",
            hold,
            user_id,
            _now(),
        )
        self._tell(changed)
        return changed is not None

    def release_abandoned(self) -> None:
        """Every hold still open, for when nothing can be working on one: the process that held them is gone."""
        with self._db.connect() as conn:
            conn.execute("UPDATE credits SET state = 'released' WHERE state = 'held'")

    def _change(self, statement: str, *params: object) -> int | None:
        """Runs an UPDATE ... RETURNING user_id on one row; whose it was, or None when no row qualified."""
        with self._db.connect() as conn:
            rows = conn.execute(statement, params).fetchall()
        return rows[0][0] if rows else None

    def _tell(self, user_id: int | None) -> None:
        if user_id is not None:
            self._db.account_changes.publish(user_id, AccountChange.CREDITS)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _after(window: timedelta) -> str:
    return (datetime.now(UTC) + window).isoformat()


def _balance(conn: sqlite3.Connection, user_id: int) -> int:
    return conn.execute(f"SELECT COALESCE(SUM(amount), 0) FROM credits WHERE user_id = ? AND {COUNTS}", (user_id, _now())).fetchone()[0]


def _add_row(
    conn: sqlite3.Connection, user_id: int, amount: int, kind: str, detail: str | None, granted_by: int | None, state: str = "settled"
) -> int:
    cursor = conn.execute(
        "INSERT INTO credits (user_id, at, amount, kind, detail, granted_by, state) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, _now(), amount, kind, detail, granted_by, state),
    )
    return cursor.lastrowid
