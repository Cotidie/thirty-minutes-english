"""The admin comes from the environment: the site is public and no email is ever checked, so whoever signs up
first with some address must not become the admin."""

import logging
from collections.abc import Mapping

from app.accounts.passwords import MIN_LENGTH, hash_password
from app.db import Database
from app.db.accounts import is_email, normalize_email

log = logging.getLogger(__name__)


def ensure_admin_from(db: Database, env: Mapping[str, str]) -> None:
    """Creates the admin when there is none. Without usable values the app still runs, with old sessions hidden."""
    if any(user.is_admin for user in db.accounts.list_all()):
        return
    email, password = normalize_email(env.get("ADMIN_EMAIL", "")), env.get("ADMIN_PASSWORD", "")
    if not is_email(email) or len(password) < MIN_LENGTH:
        log.warning(
            "no admin yet: set ADMIN_EMAIL and ADMIN_PASSWORD (at least %d characters) in .env and restart;"
            " sessions from before accounts stay hidden until then",
            MIN_LENGTH,
        )
        return
    db.accounts.ensure_admin(email, hash_password(password))
    log.info("created the admin account %s", email)
