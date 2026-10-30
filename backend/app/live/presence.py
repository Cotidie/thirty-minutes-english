"""Who is in a session right now and what is on their screens: cursors, tabs, what they have turned over, the shared
timer. None of it is saved, and losing it costs no more than a reload. Whatever must survive goes through REST.

Messages name people by a random id for the connection and a color, never by account. Everything here runs on the
event loop, so nothing needs a lock, and the readers live in this process, so the app must run as one process."""

import asyncio
import json
import math
import re
import secrets
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

MAX_FRAME_BYTES = 1024
MAX_VIEW_KEYS = 2000
MAX_VALUE_CHARS = 32
MAX_CURSORS_PER_SECOND = 40
MAX_QUEUED = 256
MAX_ELAPSED_SECONDS = 86400
LAST_TAB = 9
KEY = re.compile(r"[a-z]+(:[a-z0-9]+)*")
MAX_KEY_CHARS = 80
ANCHOR = re.compile(r"[a-z-]+(:[0-9]+)?")
MAX_ANCHOR_CHARS = 40


class Outbox:
    """What one connection has yet to be sent. Of each person's cursor only the newest waits, in the place the first
    one took, so a slow reader falls behind by position and not by memory."""

    def __init__(self) -> None:
        self._queue: deque[dict | str] = deque()  # a message, or the id of a person whose newest cursor goes here
        self._cursors: dict[str, dict] = {}
        self._ready = asyncio.Event()
        self.overflowed = False

    def put(self, message: dict) -> None:
        self._queue.append(message)
        self.overflowed = self.overflowed or len(self._queue) > MAX_QUEUED
        self._ready.set()

    def put_cursor(self, sender_id: str, message: dict) -> None:
        if sender_id not in self._cursors:
            self._queue.append(sender_id)
        self._cursors[sender_id] = message
        self._ready.set()

    def forget_cursor(self, sender_id: str) -> None:
        self._cursors.pop(sender_id, None)

    def take(self) -> list[dict]:
        messages = []
        while self._queue:
            entry = self._queue.popleft()
            if isinstance(entry, dict):
                messages.append(entry)
            elif (cursor := self._cursors.pop(entry, None)) is not None:
                messages.append(cursor)
        self._ready.clear()
        return messages

    async def wait(self) -> None:
        await self._ready.wait()


@dataclass
class Member:
    id: str
    user_id: int
    color: int
    tab: int | None = None
    cursor: dict | None = None  # the last place they pointed at, for whoever comes in while the mouse stands still
    outbox: Outbox = field(default_factory=Outbox)
    cursor_window_start: float = -1.0
    cursors_in_window: int = 0


@dataclass
class _Timer:
    running: bool
    elapsed: float
    at: float


def color_order(creator_id: int | None, shared_ids: Iterable[int], user_id: int) -> int:
    """The maker first, then whoever it is shared with by account number; the admin, on no list, comes after them."""
    roster = ([] if creator_id is None else [creator_id]) + sorted(shared_ids)
    return roster.index(user_id) if user_id in roster else len(roster)


def _refuse_constant(name: str) -> None:
    raise ValueError(name)


def _is_tab(value: object) -> bool:
    return type(value) is int and 0 <= value <= LAST_TAB


def _is_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _is_fraction(value: object) -> bool:
    return _is_number(value) and 0 <= value <= 1


def _is_view_value(value: object) -> bool:
    return value is None or type(value) is bool or _is_number(value) or (type(value) is str and len(value) <= MAX_VALUE_CHARS)


def _is_view_key(value: object) -> bool:
    return type(value) is str and len(value) <= MAX_KEY_CHARS and KEY.fullmatch(value) is not None


def _is_anchor(value: object) -> bool:
    return type(value) is str and len(value) <= MAX_ANCHOR_CHARS and ANCHOR.fullmatch(value) is not None


def _is_elapsed(value: object) -> bool:
    return _is_number(value) and 0 <= value <= MAX_ELAPSED_SECONDS


class Room:
    """One session's people and what they share. What arrives malformed or too fast is dropped without a word."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._members: list[Member] = []
        self._view: dict[str, object] = {}
        self._timer: _Timer | None = None
        self.empty_since: float | None = None
        self._readers: dict[str, Callable[[Member, dict], None]] = {
            "cursor": self._read_cursor,
            "tab": self._read_tab,
            "view": self._read_view,
            "timer": self._read_timer,
        }

    def add(self, user_id: int, preferred_color: int) -> Member:
        member = Member(secrets.token_hex(4), user_id, self._color_for(user_id, preferred_color))
        others = self._other_accounts(member)
        for other in others:
            other.outbox.put({"type": "joined", **self._person(member)})
            if other.cursor is not None:
                member.outbox.put_cursor(other.id, other.cursor)
        self._members.append(member)
        self.empty_since = None
        return member

    def remove(self, member: Member) -> None:
        self._members.remove(member)
        for other in self._other_accounts(member):
            other.outbox.forget_cursor(member.id)
            other.outbox.put({"type": "left", "id": member.id})
        if not self._members:
            self.empty_since = self._clock()

    def welcome(self, member: Member) -> dict:
        return {
            "type": "welcome",
            "you": {"id": member.id, "color": member.color},
            "people": [self._person(other) for other in self._other_accounts(member)],
            "view": dict(self._view),
            "timer": self._timer_now(),
        }

    def handle(self, member: Member, raw: str) -> None:
        message = self._parsed(raw)
        reader = self._readers.get(message.get("type")) if message is not None else None
        if reader is not None:
            reader(member, message)

    def _parsed(self, raw: str) -> dict | None:
        if len(raw.encode()) > MAX_FRAME_BYTES:
            return None
        try:
            message = json.loads(raw, parse_constant=_refuse_constant)
        except ValueError:
            return None
        return message if isinstance(message, dict) else None

    def _read_cursor(self, member: Member, message: dict) -> None:
        tab, anchor = message.get("tab"), message.get("anchor")
        if not _is_tab(tab):
            return
        if anchor is None:
            self._send_cursor(member, None, {"type": "cursor", "id": member.id, "tab": tab, "anchor": None})
            return
        x, y = message.get("x"), message.get("y")
        if _is_anchor(anchor) and _is_fraction(x) and _is_fraction(y) and self._within_cursor_rate(member):
            place = {"type": "cursor", "id": member.id, "tab": tab, "anchor": anchor, "x": x, "y": y}
            self._send_cursor(member, place, place)

    def _send_cursor(self, member: Member, standing: dict | None, message: dict) -> None:
        member.cursor = standing
        for other in self._other_accounts(member):
            other.outbox.put_cursor(member.id, message)

    def _within_cursor_rate(self, member: Member) -> bool:
        now = self._clock()
        if now - member.cursor_window_start >= 1:
            member.cursor_window_start, member.cursors_in_window = now, 0
        member.cursors_in_window += 1
        return member.cursors_in_window <= MAX_CURSORS_PER_SECOND

    def _read_tab(self, member: Member, message: dict) -> None:
        tab = message.get("tab")
        if not _is_tab(tab):
            return
        member.tab = tab
        for other in self._other_accounts(member):
            other.outbox.put({"type": "tab", "id": member.id, "tab": tab})

    def _read_view(self, member: Member, message: dict) -> None:
        key, value, seq = message.get("key"), message.get("value"), message.get("seq")
        if not (_is_view_key(key) and "value" in message and _is_view_value(value) and type(seq) is int):
            return
        if key not in self._view and len(self._view) >= MAX_VIEW_KEYS:
            return
        self._view[key] = value
        self._send_to_everyone({"type": "view", "key": key, "value": value, "by": member.id, "seq": seq})

    def _read_timer(self, member: Member, message: dict) -> None:
        running, elapsed, seq = message.get("running"), message.get("elapsed"), message.get("seq")
        if not (type(running) is bool and _is_elapsed(elapsed) and type(seq) is int):
            return
        self._timer = _Timer(running, elapsed, self._clock())
        self._send_to_everyone({"type": "timer", "running": running, "elapsed": elapsed, "by": member.id, "seq": seq})

    def _send_to_everyone(self, message: dict) -> None:
        """Back to the sender too: everyone then applies the same writes in the same order and ends on the same value."""
        for member in self._members:
            member.outbox.put(message)

    def _timer_now(self) -> dict | None:
        if self._timer is None:
            return None
        ran = self._clock() - self._timer.at if self._timer.running else 0
        return {"running": self._timer.running, "elapsed": int(self._timer.elapsed + ran)}

    def _color_for(self, user_id: int, preferred: int) -> int:
        taken = {member.color for member in self._members}
        for member in self._members:
            if member.user_id == user_id:
                return member.color
        if preferred not in taken:
            return preferred
        return next(color for color in range(len(taken) + 1) if color not in taken)

    def _other_accounts(self, member: Member) -> list[Member]:
        return [other for other in self._members if other.user_id != member.user_id]

    @staticmethod
    def _person(member: Member) -> dict:
        return {"id": member.id, "color": member.color, "tab": member.tab}


class Rooms:
    """Every room, from the first person in until `keep_seconds` after the last one out, so that one person alone can
    reload without losing the timer."""

    def __init__(self, keep_seconds: float = 600, clock: Callable[[], float] = time.monotonic) -> None:
        self._keep_seconds = keep_seconds
        self._clock = clock
        self._rooms: dict[int, Room] = {}

    def join(self, session_id: int, user_id: int, preferred_color: int) -> tuple[Room, Member]:
        self._forget_stale()
        room = self._rooms.get(session_id)
        if room is None:
            room = self._rooms[session_id] = Room(self._clock)
        return room, room.add(user_id, preferred_color)

    def leave(self, session_id: int, member: Member) -> None:
        self._rooms[session_id].remove(member)
        self._forget_stale()

    def _forget_stale(self) -> None:
        now = self._clock()
        for session_id, room in list(self._rooms.items()):
            if room.empty_since is not None and now - room.empty_since > self._keep_seconds:
                del self._rooms[session_id]
