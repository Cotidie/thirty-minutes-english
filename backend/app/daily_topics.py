"""The topics offered on the home page: half from the curated pool, half pulled
from the day's news. The news half is fetched once a day in the background and
kept, so the list is stable while you use it and different tomorrow."""

import logging
from datetime import UTC, date, datetime
from typing import Protocol

from app.claude_cli import ClaudeCli, GenerationError, structured_output
from app.models import Category, Topic, TopicListing
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
Search with firecrawl_search when it is offered; if it is missing or fails, use WebSearch instead. \
If neither works, or the searches return nothing usable, return an empty list. Never invent a story, and never return placeholder text or a note about the tools you were given. \
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
        # The day whose news fetch is running right now, and how many times
        # the pool half has been redealt today.
        self._inflight: str | None = None
        self._salt = 0
        # Why the last fetch brought nothing, for the screen. Cleared when one succeeds.
        self._error: str | None = None

    def today(self) -> date:
        return datetime.now(UTC).date()

    def listing(self) -> TopicListing:
        """The day's topics, whether a fetch is still on its way, and the last failure."""
        day = self.today()
        fresh = self.store.get_daily_topics(day.isoformat()) or []
        pool = pool_for_day(day, POOL_COUNT + FRESH_COUNT - len(fresh), exclude=fresh, salt=self._salt)
        news = [Topic(text=t, category=Category.NEWS) for t in fresh]
        return TopicListing(topics=news + pool, pending=self._inflight == day.isoformat(), error=self._error)

    def ensure_fetched(self) -> None:
        """Starts the day's fetch if it has not run yet. Safe to call on every request."""
        day = self.today().isoformat()
        if self.source is None or self._inflight == day or self.store.get_daily_topics(day) is not None:
            return
        self._start(day)

    def refresh(self) -> None:
        """Deals a new pool half now and fetches the news half again in the background."""
        day = self.today().isoformat()
        self._salt += 1
        if self.source is None or self._inflight == day:
            return
        self._start(day)

    def _start(self, day: str) -> None:
        self._inflight = day
        if self._executor is None:
            self._fetch(day)
        else:
            self._executor.submit(self._fetch, day)

    def _fetch(self, day: str) -> None:
        assert self.source is not None
        try:
            self._keep(day, self.source.fetch(FRESH_COUNT))
        except (GenerationError, KeyError, TypeError) as e:
            self._error = str(e)
            log.warning("could not fetch today's topics, staying on the pool: %s", e)
        finally:
            self._inflight = None

    def _keep(self, day: str, topics: list[str]) -> None:
        if not topics:
            # Nothing cleared the bar, or the CLI had no working search tool. Leave the
            # day unset so a later request tries again rather than caching an empty half.
            self._error = "the search brought back no stories (is web search working for the claude CLI?)"
            log.warning("no news topics came back for %s, staying on the pool", day)
            return
        self._error = None
        self.store.set_daily_topics(day, topics)
        log.info("topics for %s: %d from the news", day, len(topics))
