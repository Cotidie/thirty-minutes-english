"""The admin comes from the environment: the site is public and no email is ever checked, so whoever signs up
first with some address must not become the admin. Whoever can edit .env is the admin, so ADMIN_PASSWORD also
sets the existing admin's password."""

import logging
from collections.abc import Mapping

from app.accounts.passwords import MIN_LENGTH, hash_password, verify_password
from app.db import Database
from app.db.accounts import is_email, normalize_email
from app.models import User

log = logging.getLogger(__name__)


def _create_admin(db: Database, email: str, password: str) -> None:
    """Without usable values the app still runs, with old sessions hidden."""
    if not is_email(email) or len(password) < MIN_LENGTH:
        log.warning(
            "no admin yet: set ADMIN_EMAIL and ADMIN_PASSWORD (at least %d characters) in .env and restart;"
            " sessions from before accounts stay hidden until then",
            MIN_LENGTH,
        )
        return
    db.accounts.ensure_admin(email, hash_password(password))
    log.info("created the admin account %s", email)


def _update_admin_password(db: Database, admin: User, password: str) -> None:
    """A blank value leaves the password alone. A new one ends the admin's logins; the same one, on every restart, does not."""
    if not password:
        return
    if len(password) < MIN_LENGTH:
        log.warning("ignored ADMIN_PASSWORD: it needs at least %d characters", MIN_LENGTH)
        return
    found = db.accounts.with_hash(admin.email)
    if found is not None and verify_password(password, found[1]):
        return
    db.accounts.set_password(admin.id, hash_password(password))
    log.info("changed the admin's password from ADMIN_PASSWORD")


def ensure_admin_from(db: Database, env: Mapping[str, str]) -> None:
    password = env.get("ADMIN_PASSWORD", "")
    admin = next((user for user in db.accounts.list_all() if user.is_admin), None)
    if admin is None:
        _create_admin(db, normalize_email(env.get("ADMIN_EMAIL", "")), password)
    else:
        _update_admin_password(db, admin, password)
