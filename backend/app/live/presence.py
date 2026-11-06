"""Who is in a session right now and what is on their screens: cursors, tabs, what they have turned over, the shared
timer, and a read-aloud round in progress. None of it is saved, and losing it costs no more than a reload. Whatever must
survive goes through REST.

Messages tell people apart by a random id for the connection, and show them by a color and their username: never by
account number or email. A username changed while someone is here shows from their next connection. Everything here runs on the
event loop, so nothing needs a lock, and the readers live in this process, so the app must run as one process."""

import asyncio
import json
import math
import re
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

MAX_FRAME_BYTES = 1024
MAX_VIEW_KEYS = 2000
MAX_VALUE_CHARS = 32
MAX_CURSORS_PER_SECOND = 40
MAX_WRITES_PER_SECOND = 40  # view, tab and timer together, by account: more than holding a key down makes
MAX_QUEUED = 256
MAX_ELAPSED_SECONDS = 86400
LAST_TAB = 9
KEY = re.compile(r"[a-z]+(:[a-z0-9]+)*")
MAX_KEY_CHARS = 80
ANCHOR = re.compile(r"[a-z-]+(:[0-9]+)?")
MAX_ANCHOR_CHARS = 40
# A read-aloud round carries every mark so far and all that was heard, so its frame may be bigger than the others.
MAX_ROUND_FRAME_BYTES = 65536
MAX_HEARD_CHARS = 4000
MAX_FINDINGS = 200
MAX_SOUNDS = 32
MAX_WORD_CHARS = 64
MAX_PHONEME_CHARS = 16
ROUND_PHASES = {"reading", "done"}  # reading: the reader is connecting or listening; done: the marks are final


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

    def overflow(self) -> None:
        """Whatever else waits, this connection is to be closed, to come back from a fresh welcome."""
        self.overflowed = True
        self._ready.set()

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
class _Rate:
    """How many have come in the current second."""

    window_start: float = -1.0
    count: int = 0

    def allows(self, limit: int, now: float) -> bool:
        if now - self.window_start >= 1:
            self.window_start, self.count = now, 0
        self.count += 1
        return self.count <= limit


@dataclass
class Member:
    id: str
    user_id: int
    name: str
    color: int
    tab: int | None = None
    cursor: dict | None = None  # the last place they pointed at, for whoever comes in while the mouse stands still
    round: dict | None = None  # the read-aloud round they are in, until they close it or leave
    outbox: Outbox = field(default_factory=Outbox)
    cursor_rate: _Rate = field(default_factory=_Rate)


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


def _is_text(value: object, most: int) -> bool:
    return type(value) is str and len(value) <= most


def _is_score(value: object) -> bool:
    return _is_number(value) and 0 <= value <= 100


def _list_of(value: object, most: int, item: Callable[[object], dict | None]) -> list[dict] | None:
    """Every item rebuilt by `item`, or None when the list or any item in it is not one."""
    if type(value) is not list or len(value) > most:
        return None
    items = [item(entry) for entry in value]
    return None if None in items else items


def _sound_of(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    phoneme, score, weak = value.get("phoneme"), value.get("score"), value.get("weak")
    if not (_is_text(phoneme, MAX_PHONEME_CHARS) and _is_score(score) and type(weak) is bool):
        return None
    sound = {"phoneme": phoneme, "score": score, "weak": weak}
    if "heard" in value:
        if not _is_text(value["heard"], MAX_PHONEME_CHARS):
            return None
        sound["heard"] = value["heard"]
    return sound


def _finding_of(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    word, heard, fix = value.get("word"), value.get("heard"), value.get("fix")
    at, score, repeated_ok = value.get("at"), value.get("score"), value.get("repeated_ok")
    sounds = _list_of(value.get("sounds"), MAX_SOUNDS, _sound_of)
    if not (all(_is_text(text, MAX_WORD_CHARS) for text in (word, heard, fix)) and type(at) is int and at >= -1):
        return None
    if not (_is_score(score) and type(repeated_ok) is bool and sounds is not None):
        return None
    return {"word": word, "heard": heard, "fix": fix, "at": at, "score": score, "repeated_ok": repeated_ok, "sounds": sounds}


def _round_of(value: object) -> dict | None:
    """The round rebuilt from what a round has, or None when it is not one. A round of None is read before this."""
    if not isinstance(value, dict):
        return None
    paragraph, phase, heard = value.get("paragraph"), value.get("phase"), value.get("heard")
    findings = _list_of(value.get("findings"), MAX_FINDINGS, _finding_of)
    if not (type(paragraph) is int and paragraph > 0 and phase in ROUND_PHASES and _is_text(heard, MAX_HEARD_CHARS)):
        return None
    if findings is None:
        return None
    return {"paragraph": paragraph, "phase": phase, "heard": heard, "findings": findings}


class Room:
    """One session's people and what they share. What arrives malformed is dropped without a word, and so is a cursor
    that comes too fast. A write that comes too fast also closes the connection that sent it."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._members: list[Member] = []
        self._view: dict[str, object] = {}
        self._timer: _Timer | None = None
        self._write_rates: defaultdict[int, _Rate] = defaultdict(_Rate)
        self.empty_since: float | None = None
        self._readers: dict[str, Callable[[Member, dict], None]] = {
            "cursor": self._read_cursor,
            "tab": self._read_tab,
            "view": self._read_view,
            "timer": self._read_timer,
            "round": self._read_round,
        }

    def add(self, user_id: int, name: str, preferred_color: int) -> Member:
        member = Member(secrets.token_hex(4), user_id, name, self._color_for(user_id, preferred_color))
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
            "rounds": {other.id: other.round for other in self._other_accounts(member) if other.round is not None},
        }

    def handle(self, member: Member, raw: str) -> None:
        size = len(raw.encode())
        message = self._parsed(raw, size)
        if message is None or (message.get("type") != "round" and size > MAX_FRAME_BYTES):
            return
        reader = self._readers.get(message.get("type"))
        if reader is not None:
            reader(member, message)

    def _parsed(self, raw: str, size: int) -> dict | None:
        if size > MAX_ROUND_FRAME_BYTES:
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
        return member.cursor_rate.allows(MAX_CURSORS_PER_SECOND, self._clock())

    def _within_write_rate(self, member: Member) -> bool:
        """Counted by account, so another connection buys no more. Writes pile up in everyone's outbox, so this is what
        keeps one person from closing the others. Whoever goes past it is closed rather than ignored: their screen would
        go on waiting for a write that was dropped to come back."""
        if self._write_rates[member.user_id].allows(MAX_WRITES_PER_SECOND, self._clock()):
            return True
        member.outbox.overflow()
        return False

    def _read_tab(self, member: Member, message: dict) -> None:
        tab = message.get("tab")
        if not _is_tab(tab) or not self._within_write_rate(member):
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
        if not self._within_write_rate(member):
            return
        self._view[key] = value
        self._send_to_everyone({"type": "view", "key": key, "value": value, "by": member.id, "seq": seq})

    def _read_timer(self, member: Member, message: dict) -> None:
        running, elapsed, seq = message.get("running"), message.get("elapsed"), message.get("seq")
        if not (type(running) is bool and _is_elapsed(elapsed) and type(seq) is int):
            return
        if not self._within_write_rate(member):
            return
        self._timer = _Timer(running, elapsed, self._clock())
        self._send_to_everyone({"type": "timer", "running": running, "elapsed": elapsed, "by": member.id, "seq": seq})

    def _read_round(self, member: Member, message: dict) -> None:
        """Each reader writes only their own round, so it goes to the others without coming back. Not to the reader's other
        connections either, as with cursors: those have no one by that id to name."""
        if "round" not in message:
            return
        sent = message["round"]
        read = None if sent is None else _round_of(sent)
        if (sent is not None and read is None) or not self._within_write_rate(member):
            return
        member.round = read
        for other in self._other_accounts(member):
            other.outbox.put({"type": "round", "id": member.id, "round": read})

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
        return {"id": member.id, "name": member.name, "color": member.color, "tab": member.tab}


class Rooms:
    """Every room, from the first person in until `keep_seconds` after the last one out, so that one person alone can
    reload without losing the timer."""

    def __init__(self, keep_seconds: float = 600, clock: Callable[[], float] = time.monotonic) -> None:
        self._keep_seconds = keep_seconds
        self._clock = clock
        self._rooms: dict[int, Room] = {}

    def join(self, session_id: int, user_id: int, name: str, preferred_color: int) -> tuple[Room, Member]:
        self._forget_stale()
        room = self._rooms.get(session_id)
        if room is None:
            room = self._rooms[session_id] = Room(self._clock)
        return room, room.add(user_id, name, preferred_color)

    def leave(self, session_id: int, member: Member) -> None:
        self._rooms[session_id].remove(member)
        self._forget_stale()

    def _forget_stale(self) -> None:
        now = self._clock()
        for session_id, room in list(self._rooms.items()):
            if room.empty_since is not None and now - room.empty_since > self._keep_seconds:
                del self._rooms[session_id]
