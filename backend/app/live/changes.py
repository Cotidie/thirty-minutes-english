"""What changed, for whoever is following: a session someone has open, or the list of sessions an account sees. REST
owns the state: a change is only the name of what to read again, and it holds no data. Repositories publish it after
they commit; the event streams read it.

The readers live in this process, so the app must run as one process."""

import asyncio
from enum import StrEnum
from threading import Lock


class SessionChange(StrEnum):
    SESSION = "session"
    STARS = "stars"
    NOTE = "note"
    RECORDS = "records"
    SHARES = "shares"
    ACCESS = "access"  # someone may have lost the session; the stream checks, and this never reaches a browser


class AccountChange(StrEnum):
    SESSIONS = "sessions"  # the list of sessions the account sees


type Change = SessionChange | AccountChange


class Subscription:
    """What one reader has not seen yet: a set, not a queue, so a slow reader costs no memory and a burst
    of one change arrives as one."""

    def __init__(self, changes: "Changes", key: int, loop: asyncio.AbstractEventLoop) -> None:
        self._changes = changes
        self._key = key
        self._loop = loop
        self._pending: set[Change] = set()
        self._wake = asyncio.Event()

    def _add(self, change: Change) -> None:
        self._pending.add(change)
        self._wake.set()

    def notify(self, change: Change) -> None:
        """From any thread. A reader whose loop has ended hears nothing."""
        try:
            self._loop.call_soon_threadsafe(self._add, change)
        except RuntimeError:
            pass

    async def next(self, timeout: float) -> set[Change]:
        """What changed since the last call; empty when nothing did within `timeout` seconds."""
        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except TimeoutError:
            return set()
        self._wake.clear()
        changed, self._pending = self._pending, set()
        return changed

    def close(self) -> None:
        self._changes.remove(self._key, self)


class Changes:
    """The readers of one kind of thing, by its id: `Database` keeps one of these for sessions and one for accounts."""

    def __init__(self) -> None:
        self._readers: dict[int, set[Subscription]] = {}
        self._lock = Lock()

    def subscribe(self, key: int) -> Subscription:
        """From the reader's running event loop."""
        subscription = Subscription(self, key, asyncio.get_running_loop())
        with self._lock:
            self._readers.setdefault(key, set()).add(subscription)
        return subscription

    def remove(self, key: int, subscription: Subscription) -> None:
        with self._lock:
            readers = self._readers.get(key, set())
            readers.discard(subscription)
            if not readers:
                self._readers.pop(key, None)

    def publish(self, key: int, change: Change) -> None:
        """From any thread: repositories run on the thread pool and on the job threads."""
        with self._lock:
            readers = list(self._readers.get(key, ()))
        for reader in readers:
            reader.notify(change)
