"""The name others know an account by: what they search for to share a session, and what labels its cursor. It is not
a login: the email is. Korean is allowed, so it is compared after NFC, and English letters without regard to case."""

import re
import secrets
import unicodedata

MIN_LENGTH = 2
MAX_LENGTH = 20
USERNAME = re.compile(rf"[0-9A-Za-z_가-힣]{{{MIN_LENGTH},{MAX_LENGTH}}}")
RULE = f"Use {MIN_LENGTH} to {MAX_LENGTH} Korean or English letters, digits or _, with no spaces."


def normalize_username(name: str) -> str:
    """One spelling for what looks the same: a Mac types Korean decomposed, which would never match it composed."""
    return unicodedata.normalize("NFC", name).strip()


def is_username(name: str) -> bool:
    return USERNAME.fullmatch(name) is not None


def random_username() -> str:
    """A placeholder for an account that never chose a name; its owner can change it."""
    return f"user_{secrets.token_hex(3)}"
