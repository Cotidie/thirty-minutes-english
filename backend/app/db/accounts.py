"""Accounts and their logins. A login is a random token in the browser's cookie; only its hash is kept."""

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models import User

if TYPE_CHECKING:
    from app.db import Database

LOGIN_LIFETIME = timedelta(days=30)
USER_COLUMNS = "id, created_at, email, is_admin, can_create"


class EmailTaken(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_from(row: sqlite3.Row) -> User:
    return User(**{column: row[column] for column in USER_COLUMNS.split(", ")})


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AccountRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def create(self, email: str, password_hash: str) -> User:
        """Raises EmailTaken when an account already uses the email."""
        try:
            with self._db.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO users (created_at, email, password_hash) VALUES (?, ?, ?)",
                    (datetime.now(UTC).isoformat(), normalize_email(email), password_hash),
                )
        except sqlite3.IntegrityError:
            raise EmailTaken(email) from None
        assert cur.lastrowid is not None
        user = self.get(cur.lastrowid)
        assert user is not None
        return user

    def get(self, user_id: int) -> User | None:
        with self._db.connect() as conn:
            row = conn.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()
        return user_from(row) if row else None

    def by_email(self, email: str) -> User | None:
        with self._db.connect() as conn:
            row = conn.execute(f"SELECT {USER_COLUMNS} FROM users WHERE email = ?", (normalize_email(email),)).fetchone()
        return user_from(row) if row else None

    def with_hash(self, email: str) -> tuple[User, str] | None:
        """The account and its password hash, to check a login against."""
        with self._db.connect() as conn:
            row = conn.execute(
                f"SELECT {USER_COLUMNS}, password_hash FROM users WHERE email = ?", (normalize_email(email),)
            ).fetchone()
        return (user_from(row), row["password_hash"]) if row else None

    def list_all(self) -> list[User]:
        with self._db.connect() as conn:
            rows = conn.execute(f"SELECT {USER_COLUMNS} FROM users ORDER BY id").fetchall()
        return [user_from(row) for row in rows]

    def set_can_create(self, user_id: int, value: bool) -> User | None:
        with self._db.connect() as conn:
            conn.execute("UPDATE users SET can_create = ? WHERE id = ?", (int(value), user_id))
        return self.get(user_id)

    def set_password(self, user_id: int, password_hash: str) -> None:
        """Every login of the account ends with its old password."""
        with self._db.connect() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
            conn.execute("DELETE FROM logins WHERE user_id = ?", (user_id,))

    def start_login(self, user_id: int) -> str:
        """The token for the cookie. Logins past their time go now, since nothing else reads them."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with self._db.connect() as conn:
            conn.execute("DELETE FROM logins WHERE expires_at <= ?", (now.isoformat(),))
            conn.execute(
                "INSERT INTO logins (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_digest(token), user_id, (now + LOGIN_LIFETIME).isoformat()),
            )
        return token

    def user_of_login(self, token: str) -> User | None:
        """Who the token logs in, while it lasts."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT u.id, u.created_at, u.email, u.is_admin, u.can_create FROM logins l JOIN users u ON u.id = l.user_id"
                " WHERE l.token_hash = ? AND l.expires_at > ?",
                (_digest(token), datetime.now(UTC).isoformat()),
            ).fetchone()
        return user_from(row) if row else None

    def end_login(self, token: str) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM logins WHERE token_hash = ?", (_digest(token),))

    def ensure_admin(self, email: str, password_hash: str) -> User | None:
        """The admin, the first time there is none: an account with that email is taken over, its logins ended,
        and every session with no creator becomes the admin's. None when there already is an admin."""
        address = normalize_email(email)
        with self._db.connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE is_admin = 1").fetchone():
                return None
            row = conn.execute("SELECT id FROM users WHERE email = ?", (address,)).fetchone()
            if row:
                user_id = row["id"]
                conn.execute("UPDATE users SET password_hash = ?, is_admin = 1 WHERE id = ?", (password_hash, user_id))
                conn.execute("DELETE FROM logins WHERE user_id = ?", (user_id,))
            else:
                user_id = conn.execute(
                    "INSERT INTO users (created_at, email, password_hash, is_admin) VALUES (?, ?, ?, 1)",
                    (datetime.now(UTC).isoformat(), address, password_hash),
                ).lastrowid
            conn.execute("UPDATE sessions SET created_by = ? WHERE created_by IS NULL", (user_id,))
        assert user_id is not None
        return self.get(user_id)
