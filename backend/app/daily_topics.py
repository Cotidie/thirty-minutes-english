"""The topics offered on the home page: half from the curated pool, half pulled
from the day's news. The news half is fetched once a day in the background and
kept, so the list is stable while you use it and different tomorrow."""

import logging
from datetime import UTC, date, datetime
from typing import Protocol

from app.claude_cli import ClaudeCli, GenerationError, structured_output
from app.models import Category, Topic
from app.store import SessionStore
from app.topics import pool_for_day

log = logging.getLogger(__name__)

FRESH_COUNT = 6
POOL_COUNT = 6

TOPICS_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topics"],
    "properties": {
        "topics": {
            "type": "array",
            "minItems": 0,  # an empty list is how a run with no web access reports failure
            "maxItems": FRESH_COUNT,
            "items": {"type": "string"},
        }
    },
}

PROMPT = """Search the news from the last seven days and give me {count} topics for a short English \
article a pair of adult learners will argue about over coffee today.

Take only stories that ran big. A story qualifies if it led the front page or the top of the home page \
at major international outlets (Reuters, AP, BBC, the Financial Times, The New York Times, The Guardian, \
The Economist, Nikkei, Al Jazeera), or if it broke in the last day or two and is climbing fast. \
Two independent major outlets covering it prominently is the bar. If you cannot tell that a story \
cleared it, drop it and take the next one. Leave out trade-press items, single-company product news, \
and local stories with no wider consequence.

Each topic is one line: a noun phrase of at most 10 words, in plain English, naming the dispute rather \
than reporting the headline. "Who pays when the grid runs short" rather than "Country X raises power \
prices 12%". No dates, no figures, and no story that only makes sense to people who followed it all week.

Spread them out: no two on the same story, and between them cover more than one region and more than one \
field. At least one should sit near technology, industry or science. Skip anything whose only angle is \
party politics or a running war's daily movements, and skip celebrity news.

Run at most 4 searches, and spend one of them on what the major outlets are leading with right now. \
If you have no web search tool in this session, or the searches return nothing usable, return an empty \
list. Never invent a story, and never return placeholder text or a note about the tools you were given. \
Return only the structured output."""


class TopicSource(Protocol):
    def fetch(self, count: int) -> list[str]: ...


class ClaudeTopicSource:
    def __init__(self, model: str = "sonnet", effort: str = "medium", timeout_s: float = 240):
        self._cli = ClaudeCli(model=model, effort=effort, timeout_s=timeout_s)

    def fetch(self, count: int) -> list[str]:
        envelope = self._cli.run(PROMPT.format(count=count), TOPICS_SCHEMA)
        topics = structured_output(envelope)["topics"]
        return [t.strip() for t in topics if t.strip()]


class DailyTopics:
    """Today's list, and the background refresh that fills its news half."""

    def __init__(self, store: SessionStore, source: TopicSource | None, executor=None):
        self.store = store
        self.source = source
        self._executor = executor
        self._running: str | None = None
        # A manual refresh: the day whose news half is being fetched again, and
        # how many times the pool half has been redealt today.
        self._refreshing: str | None = None
        self._salt = 0

    def today(self) -> date:
        return datetime.now(UTC).date()

    def listing(self) -> tuple[list[Topic], bool]:
        """The day's topics, and whether a fetch is still on its way."""
        day = self.today()
        fresh = self.store.get_daily_topics(day.isoformat()) or []
        pool = pool_for_day(day, POOL_COUNT + FRESH_COUNT - len(fresh), exclude=fresh, salt=self._salt)
        pending = self.source is not None and (not fresh or self._refreshing == day.isoformat())
        news = [Topic(text=t, category=Category.NEWS) for t in fresh]
        return news + pool, pending

    def ensure_fetched(self) -> None:
        """Starts the day's fetch if it has not run yet. Safe to call on every request."""
        day = self.today().isoformat()
        if self.source is None or self._running == day or self.store.get_daily_topics(day) is not None:
            return
        self._start(day)

    def refresh(self) -> None:
        """Deals a new pool half now and fetches the news half again in the background."""
        day = self.today().isoformat()
        self._salt += 1
        if self.source is None or self._refreshing == day:
            return
        self._refreshing = day
        self._start(day)

    def _start(self, day: str) -> None:
        self._running = day
        if self._executor is None:
            self._fetch(day)
        else:
            self._executor.submit(self._fetch, day)

    def _fetch(self, day: str) -> None:
        assert self.source is not None
        try:
            topics = self.source.fetch(FRESH_COUNT)
        except (GenerationError, KeyError, TypeError) as e:
            log.warning("could not fetch today's topics, staying on the pool: %s", e)
            self._done(day, fetched=False)
            return
        if not topics:
            # No web access, or nothing cleared the bar. Leave the day unset so a
            # later request tries again rather than caching an empty news half.
            log.warning("no news topics came back for %s, staying on the pool", day)
            self._done(day, fetched=False)
            return
        self.store.set_daily_topics(day, topics)
        log.info("topics for %s: %d from the news", day, len(topics))
        self._done(day, fetched=True)

    def _done(self, day: str, fetched: bool) -> None:
        if not fetched:
            self._running = None
        if self._refreshing == day:
            self._refreshing = None
