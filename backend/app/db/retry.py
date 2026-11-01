"""Writes that must not be lost to a moment's contention on the one SQLite file."""

import logging
import sqlite3
import time
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

ATTEMPTS = 3
WAIT_SECONDS = 1.0


def when_free(write: Callable[[], T]) -> T:
    """What the write returns, tried again while the database refuses it. Raises what the last try raised."""
    for _ in range(ATTEMPTS - 1):
        try:
            return write()
        except sqlite3.OperationalError as e:
            log.warning("the database refused a write, trying again: %s", e)
            time.sleep(WAIT_SECONDS)
    return write()
