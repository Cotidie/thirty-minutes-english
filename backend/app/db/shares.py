"""Who may open a session: its creator, whoever it is shared with, and the admin. Every check of that is here."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.db.accounts import user_from
from app.live.changes import AccountChange, SessionChange
from app.models import User

if TYPE_CHECKING:
    from app.db import Database


# The sessions an account made or had shared with it: what its home page lists and what it has already seen.
# Takes the account's id twice.
VISIBLE_SESSIONS = "SELECT id FROM sessions WHERE created_by = ? UNION SELECT session_id FROM session_shares WHERE user_id = ?"
# The other way round: the accounts whose home page lists a session. Takes the session's id twice.
ACCOUNTS_LISTING = (
    "SELECT created_by FROM sessions WHERE id = ? AND created_by IS NOT NULL"
    " UNION SELECT user_id FROM session_shares WHERE session_id = ?"
)


class ShareRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def share(self, session_id: int, user_id: int) -> None:
        """Sharing again changes nothing."""
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO session_shares (session_id, user_id, created_at) VALUES (?, ?, ?)",
                (session_id, user_id, datetime.now(UTC).isoformat()),
            )
        if cur.rowcount > 0:
            self._db.changes.publish(session_id, SessionChange.SHARES)
            self._db.account_changes.publish(user_id, AccountChange.SESSIONS)

    def unshare(self, session_id: int, user_id: int) -> bool:
        """Whether there was a share to end."""
        with self._db.connect() as conn:
            cur = conn.execute("DELETE FROM session_shares WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        if cur.rowcount == 0:
            return False
        self._db.changes.publish(session_id, SessionChange.ACCESS)
        self._db.changes.publish(session_id, SessionChange.SHARES)
        self._db.account_changes.publish(user_id, AccountChange.SESSIONS)
        return True

    def shared_with(self, session_id: int) -> list[User]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT u.id, u.created_at, u.email, u.is_admin, u.can_create FROM session_shares s"
                " JOIN users u ON u.id = s.user_id WHERE s.session_id = ? ORDER BY u.email",
                (session_id,),
            ).fetchall()
        return [user_from(row) for row in rows]

    def created_by(self, session_id: int) -> int | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT created_by FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row[0] if row else None

    def can_access(self, user: User, session_id: int) -> bool:
        with self._db.connect() as conn:
            row = conn.execute("SELECT created_by FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return False
            if user.is_admin or row[0] == user.id:
                return True
            return (
                conn.execute("SELECT 1 FROM session_shares WHERE session_id = ? AND user_id = ?", (session_id, user.id)).fetchone()
                is not None
            )

    def has_sessions(self, user_id: int) -> bool:
        """Whether the account made a session or had one shared with it."""
        with self._db.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM sessions WHERE created_by = ? UNION ALL SELECT 1 FROM session_shares WHERE user_id = ? LIMIT 1",
                    (user_id, user_id),
                ).fetchone()
                is not None
            )

    def can_see_picture(self, user: User, picture_id: int) -> bool:
        """Whether a session the user may open shows the picture; picture ids run in order, so a login is not enough."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT session_id FROM vocabulary WHERE picture_id = ? OR example_picture_id = ?"
                " UNION SELECT session_id FROM figures WHERE picture_id = ?",
                (picture_id, picture_id, picture_id),
            ).fetchall()
        return any(self.can_access(user, row[0]) for row in rows)
