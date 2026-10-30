"""Passwords as scrypt hashes, the parameters kept in the stored string so they can change later."""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**15, 8, 1
MAX_MEMORY = 64 * 1024 * 1024  # scrypt takes 128 * N * R bytes, about 32 MB
SALT_BYTES = 16


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=MAX_MEMORY, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        return hmac.compare_digest(_derive(password, base64.b64decode(salt), int(n), int(r), int(p)), expected)
    except ValueError:
        return False


def burn_time() -> None:
    """As long as checking a password takes, so an unknown email answers no faster than a wrong password."""
    _derive("", bytes(SALT_BYTES), N, R, P)
