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
            "minItems": FRESH_COUNT,
            "maxItems": FRESH_COUNT,
            "items": {"type": "string"},
        }
    },
}

PROMPT = """Search the news from the last seven days and give me {count} topics for a short English \
article a pair of adult learners will argue about over coffee today.

Each topic is one line: a noun phrase of at most 10 words, in plain English, naming the dispute rather \
than reporting the headline. "Who pays when the grid runs short" rather than "Country X raises power \
prices 12%". No dates, no figures, and no story that only makes sense to people who followed it all week.

Spread them out: no two on the same story, and between them cover more than one region and more than one \
field. At least one should sit near technology, industry or science. Skip anything whose only angle is \
party politics or a running war's daily movements, and skip celebrity news.

Run at most 3 searches. Return only the structured output."""


class TopicSource(Protocol):
    def fetch(self, count: int) -> list[str]: ...


class ClaudeTopicSource:
    def __init__(self, model: str = "sonnet", effort: str = "medium", timeout_s: float = 180):
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

    def today(self) -> date:
        return datetime.now(UTC).date()

    def listing(self) -> tuple[list[Topic], bool]:
        """The day's topics, and whether a fetch is still on its way."""
        day = self.today()
        fresh = self.store.get_daily_topics(day.isoformat()) or []
        pool = pool_for_day(day, POOL_COUNT + FRESH_COUNT - len(fresh), exclude=fresh)
        pending = not fresh and self.source is not None
        news = [Topic(text=t, category=Category.NEWS) for t in fresh]
        return news + pool, pending

    def ensure_fetched(self) -> None:
        """Starts the day's fetch if it has not run yet. Safe to call on every request."""
        day = self.today().isoformat()
        if self.source is None or self._running == day or self.store.get_daily_topics(day) is not None:
            return
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
            self._running = None
            return
        if topics:
            self.store.set_daily_topics(day, topics)
        log.info("topics for %s: %d from the news", day, len(topics))
