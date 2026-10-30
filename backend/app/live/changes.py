"""What changed in a session, for whoever has it open. REST owns the state: a change is only the name of what to
read again, and it holds no data. Repositories publish it after they commit; the event stream reads it.

The readers live in this process, so the app must run as one process."""

import asyncio
from enum import StrEnum
from threading import Lock


class SessionChange(StrEnum):
    SESSION = "session"
    STARS = "stars"
    NOTE = "note"
    RECORDS = "records"
    ACCESS = "access"  # someone may have lost the session; the stream checks, and this never reaches a browser


class Subscription:
    """What one reader has not seen yet: a set, not a queue, so a slow reader costs no memory and a burst
    of one change arrives as one."""

    def __init__(self, changes: "SessionChanges", session_id: int, loop: asyncio.AbstractEventLoop) -> None:
        self._changes = changes
        self._session_id = session_id
        self._loop = loop
        self._pending: set[SessionChange] = set()
        self._wake = asyncio.Event()

    def _add(self, change: SessionChange) -> None:
        self._pending.add(change)
        self._wake.set()

    def notify(self, change: SessionChange) -> None:
        """From any thread. A reader whose loop has ended hears nothing."""
        try:
            self._loop.call_soon_threadsafe(self._add, change)
        except RuntimeError:
            pass

    async def next(self, timeout: float) -> set[SessionChange]:
        """What changed since the last call; empty when nothing did within `timeout` seconds."""
        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except TimeoutError:
            return set()
        self._wake.clear()
        changed, self._pending = self._pending, set()
        return changed

    def close(self) -> None:
        self._changes.remove(self._session_id, self)


class SessionChanges:
    def __init__(self) -> None:
        self._readers: dict[int, set[Subscription]] = {}
        self._lock = Lock()

    def subscribe(self, session_id: int) -> Subscription:
        """From the reader's running event loop."""
        subscription = Subscription(self, session_id, asyncio.get_running_loop())
        with self._lock:
            self._readers.setdefault(session_id, set()).add(subscription)
        return subscription

    def remove(self, session_id: int, subscription: Subscription) -> None:
        with self._lock:
            readers = self._readers.get(session_id, set())
            readers.discard(subscription)
            if not readers:
                self._readers.pop(session_id, None)

    def publish(self, session_id: int, change: SessionChange) -> None:
        """From any thread: repositories run on the thread pool and on the job threads."""
        with self._lock:
            readers = list(self._readers.get(session_id, ()))
        for reader in readers:
            reader.notify(change)
