"""A new password for an account, printed once. There is no email check to recover one through, so the admin runs:

    docker compose exec backend uv run --no-dev python -m app.accounts.reset_password EMAIL
"""

import os
import secrets
import sys

from app.accounts.passwords import hash_password
from app.db import Database
from app.main import ROOT


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.accounts.reset_password EMAIL", file=sys.stderr)
        return 2
    db = Database(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db"))
    user = db.accounts.by_email(argv[0])
    if user is None:
        print(f"no account uses {argv[0].strip()}", file=sys.stderr)
        return 1
    password = secrets.token_urlsafe(12)
    db.accounts.set_password(user.id, hash_password(password))
    print(f"New password for {user.email}: {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
