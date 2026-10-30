"""How often someone may try: kept in memory, so a restart forgets them. Signups are counted as a whole,
since behind the tunnel every request looks like it comes from one address."""

import time
from collections.abc import Callable
from threading import Lock


class FailedLogins:
    def __init__(self, limit: int = 10, window_s: float = 900, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._lock = Lock()

    def _recent(self, email: str, now: float) -> list[float]:
        return [t for t in self._failures.get(email, []) if now - t < self._window_s]

    def blocked(self, email: str) -> bool:
        with self._lock:
            return len(self._recent(email, self._clock())) >= self._limit

    def failed(self, email: str) -> None:
        now = self._clock()
        with self._lock:
            self._failures = {e: recent for e in self._failures if (recent := self._recent(e, now))}
            self._failures[email] = [*self._failures.get(email, []), now]

    def cleared(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)


class SignupLimit:
    def __init__(self, limit: int = 20, window_s: float = 3600, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._signups: list[float] = []
        self._lock = Lock()

    def allow(self) -> bool:
        """Counts this signup when it is allowed."""
        now = self._clock()
        with self._lock:
            self._signups = [t for t in self._signups if now - t < self._window_s]
            if len(self._signups) >= self._limit:
                return False
            self._signups.append(now)
            return True
