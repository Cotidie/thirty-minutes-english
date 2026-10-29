"""OpenRouter's image MCP server, turning prompts into PNG bytes, signed in with the OpenRouter key."""

import asyncio
import base64
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.mcp_client import McpError, McpHttp, Session, text_of

log = logging.getLogger(__name__)

OPENROUTER_MCP = "https://mcp.openrouter.ai/mcp"
DEFAULT_MODEL = "google/gemini-3-pro-image"  # Nano Banana Pro


COST = re.compile(r"cost: \$([\d.]+)")


@dataclass(frozen=True)
class Drawn:
    """One picture as a painter hands it over: the PNG, the model that drew it, how long it took,
    and what it cost where the provider says."""

    png: bytes
    model: str
    seconds: float | None = None
    cost: float | None = None


OnDrawn = Callable[[int], None]  # pictures finished so far; raising from it stops the painter
OnPicture = Callable[[int, Drawn], None]  # a prompt's index and its picture, the moment it is drawn


class PictureStats(Protocol):
    """How long a picture of a model takes here, from the pictures drawn so far."""

    def seconds(self, model: str) -> float | None: ...


class NoStats:
    def seconds(self, model: str) -> float | None:
        return None


class Painter(Protocol):
    def paint(self, prompts: list[str], on_drawn: OnDrawn | None = None, on_picture: OnPicture | None = None) -> list[Drawn | None]: ...
    def expected_seconds(self, count: int) -> float | None:
        """How long `count` pictures usually take with this model here; None until one was drawn."""


class Counter:
    """Counts finished pictures across concurrent tasks and reports each one."""

    def __init__(self, on_drawn: OnDrawn | None) -> None:
        self._on_drawn = on_drawn or (lambda _: None)
        self.done = 0

    def tick(self) -> None:
        self.done += 1
        self._on_drawn(self.done)


def painter_for(key: str, model: str, stats: PictureStats | None = None) -> Painter | None:
    """OpenRouter's painter for `model` (blank: the default), or None while the key is missing.
    `stats` says how long this model's pictures took here, for the wait a job foresees."""
    if not key:
        return None
    return OpenRouterPainter(McpHttp(OPENROUTER_MCP, key), model or DEFAULT_MODEL, stats)


class OpenRouterPainter:
    """One generate-image call per picture, all in flight on one session; the PNG comes back inline
    as base64, beside a text block that names the charge ("cost: $0.007"). Each picture is timed
    from its own call, and since they are drawn side by side, a batch takes about as long as one."""

    def __init__(self, server: McpHttp, model: str, stats: PictureStats | None = None) -> None:
        self._server = server
        self._model = model
        self._stats = stats or NoStats()

    def expected_seconds(self, count: int) -> float | None:
        return self._stats.seconds(self._model)

    def paint(self, prompts: list[str], on_drawn: OnDrawn | None = None, on_picture: OnPicture | None = None) -> list[Drawn | None]:
        return asyncio.run(self._paint(prompts, Counter(on_drawn), on_picture))

    async def _paint(self, prompts: list[str], counter: Counter, on_picture: OnPicture | None) -> list[Drawn | None]:
        async def one(session: Session, index: int, prompt: str) -> Drawn | None:
            drawn = await self._one(session, prompt)
            if drawn and on_picture:
                on_picture(index, drawn)
            counter.tick()
            return drawn

        try:
            async with self._server.session() as session:
                return list(await asyncio.gather(*(one(session, i, p) for i, p in enumerate(prompts))))
        except McpError as e:
            log.warning("openrouter could not draw the pictures: %s", e)
            return [None] * len(prompts)

    async def _one(self, session: Session, prompt: str) -> Drawn | None:
        started = time.monotonic()
        try:
            result = await session.call("generate-image", {"prompt": prompt, "model": self._model})
        except McpError as e:
            log.warning("openrouter could not draw a picture: %s", e)
            return None
        cost = COST.search(text_of(result))
        png = next((base64.b64decode(b.data) for b in result.content if b.type == "image" and b.data), None)
        if png is None:
            log.warning("openrouter returned no image block%s", f" (charged ${cost.group(1)})" if cost else "")
            return None
        return Drawn(png, self._model, time.monotonic() - started, float(cost.group(1)) if cost else None)
