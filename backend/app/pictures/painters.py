"""Image MCP servers that turn prompts into PNG bytes, signed in with the provider's API key."""

import asyncio
import base64
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx2

from app.mcp_client import McpError, McpHttp, Session, payload, text_of

log = logging.getLogger(__name__)

OPENROUTER_MCP = "https://mcp.openrouter.ai/mcp"
COMFY_MCP = "https://cloud.comfy.org/mcp"
# Provider -> default image model, Nano Banana Pro on both.
DEFAULT_MODEL = {"openrouter": "google/gemini-3-pro-image", "comfy": "vertexai/nano-banana-pro"}


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
        self.reach(self.done + 1)

    def reach(self, done: int) -> None:
        """Reports `done` finished, never fewer than before; called again with the same count it
        still reports, so a cancel gets through while nothing new finishes."""
        self.done = max(self.done, done)
        self._on_drawn(self.done)


def painter_for(provider: str, model: str, keys: dict[str, str], stats: PictureStats | None = None) -> Painter | None:
    """The painter for `provider` ("openrouter" / "comfy"), or None when it is off or its key is missing.
    `stats` says how long this model's pictures took here, for the wait a job foresees."""
    key = keys.get(provider, "")
    if provider not in DEFAULT_MODEL or not key:
        return None
    model = model or DEFAULT_MODEL[provider]
    if provider == "comfy":
        return ComfyPainter(McpHttp(COMFY_MCP, key), model, stats)
    return OpenRouterPainter(McpHttp(OPENROUTER_MCP, key), model, stats)


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


class ComfyPainter:
    """One batch for all the pictures, waited on, then the signed URLs fetched at once. comfy draws
    as many side by side as the plan allows (Standard: one at a time) and keeps the batch across
    connections, so a dropped connection reconnects and waits on, and a give-up keeps what is done.
    A picture's seconds are the batch's time shared over the pictures that came back, since the plan
    draws them one after another."""

    WAIT_ROUNDS = 24  # wait_for_batch returns after ~25 s each; about 10 minutes in all
    RECONNECTS = 2

    def __init__(self, server: McpHttp, model: str, stats: PictureStats | None = None, fetch=None) -> None:
        self._server = server
        self._model = model
        self._stats = stats or NoStats()
        self._fetch = fetch or fetch_url

    def expected_seconds(self, count: int) -> float | None:
        seconds = self._stats.seconds(self._model)
        return seconds * count if seconds is not None else None

    def paint(self, prompts: list[str], on_drawn: OnDrawn | None = None, on_picture: OnPicture | None = None) -> list[Drawn | None]:
        return asyncio.run(self._paint(prompts, Counter(on_drawn), on_picture))

    async def _paint(self, prompts: list[str], counter: Counter, on_picture: OnPicture | None) -> list[Drawn | None]:
        started = time.monotonic()
        pngs = await self._batch(prompts, counter)
        came_back = sum(1 for png in pngs if png is not None)
        each = (time.monotonic() - started) / came_back if came_back else None
        pictures = [Drawn(png, self._model, each) if png is not None else None for png in pngs]
        for index, drawn in enumerate(pictures):  # a batch hands its pictures over together, at the end
            if drawn and on_picture:
                on_picture(index, drawn)
        return pictures

    async def _batch(self, prompts: list[str], counter: Counter) -> list[bytes | None]:
        items = [
            {"tool": "partner_generate", "type": "image", "aspect_ratio": "4:3", "prompt": p, "description": f"word {i}", **self._model_fields()}
            for i, p in enumerate(prompts)
        ]
        try:
            submitted = await self._call("submit_batch", {"client_os": "linux", "confirm": True, "items": items})
            batch_id, job_ids = submitted["batch_id"], submitted["job_ids"]
        except (McpError, KeyError, TypeError) as e:
            log.warning("comfy could not take the batch: %s", e)
            return [None] * len(prompts)
        log.info("comfy batch %s: %d pictures", batch_id, len(job_ids))
        try:
            await self._wait(batch_id, counter)
        except McpError as e:
            log.warning("comfy batch %s: stopped waiting, keeping what is drawn: %s", batch_id, e)
        except BaseException:
            await self._cancel(batch_id, job_ids)
            raise
        try:
            outputs = await self._call("get_batch_output", {"batch_id": batch_id, "client_os": "linux"})
        except McpError as e:
            log.warning("comfy batch %s: could not collect the pictures: %s", batch_id, e)
            return [None] * len(prompts)
        url_of = {o["job_id"]: o["url"] for o in outputs.get("outputs", []) if o.get("url")}
        return list(await asyncio.gather(*(self._fetch_or_none(url_of.get(job)) for job in job_ids)))

    async def _wait(self, batch_id: str, counter: Counter) -> None:
        """Until every picture is ready or failed, or the rounds run out; reconnects when the connection drops."""
        rounds, reconnects = 0, 0
        while rounds < self.WAIT_ROUNDS:
            try:
                async with self._server.session() as session:
                    while rounds < self.WAIT_ROUNDS:
                        rounds += 1
                        waited = payload(await session.call("wait_for_batch", {"batch_id": batch_id}))
                        counter.reach(finished(waited))
                        if not waited.get("timed_out"):
                            return
                return
            except McpError as e:
                reconnects += 1
                if reconnects > self.RECONNECTS:
                    raise
                log.warning("comfy batch %s: connection dropped, reconnecting: %s", batch_id, e)

    async def _cancel(self, batch_id: str, job_ids: list[str]) -> None:
        """Stops the pictures still queued so a cancelled session does not keep billing."""
        try:
            async with self._server.session() as session:
                for job in job_ids:
                    try:
                        await session.call("cancel_job", {"prompt_id": job})
                    except McpError:
                        pass  # already finished
            log.info("comfy batch %s: cancelled", batch_id)
        except McpError as e:
            log.warning("comfy batch %s: could not cancel: %s", batch_id, e)

    async def _call(self, tool: str, arguments: dict):
        async with self._server.session() as session:
            return payload(await session.call(tool, arguments))

    def _model_fields(self) -> dict:
        """comfy names every OpenAI image model `openai/images-generations` and takes the variant
        in params, so `openai/gpt-image-2.5-flare` (OpenRouter's spelling) works on both providers."""
        if self._model.startswith("openai/gpt-image"):
            return {"model": "openai/images-generations", "params": {"model": self._model.removeprefix("openai/")}}
        return {"model": self._model}

    async def _fetch_or_none(self, url: str | None) -> bytes | None:
        if not url:
            return None
        try:
            return await self._fetch(url)
        except httpx2.HTTPError as e:
            log.warning("could not fetch a picture from %s: %s", url, e)
            return None


def finished(batch: dict) -> int:
    """Pictures of a comfy batch that are ready or failed, from wait_for_batch's per-job states."""
    summary = batch.get("summary") or {}
    if summary:
        return (summary.get("ready") or 0) + (summary.get("failed") or 0)
    return sum(1 for job in batch.get("jobs") or [] if job.get("state") in ("ready", "failed"))


async def fetch_url(url: str, attempts: int = 3, wait_s: float = 2, transport: httpx2.AsyncBaseTransport | None = None) -> bytes:
    """The bytes at `url`; the signed links flake, so a failed try is repeated after a short wait."""
    async with httpx2.AsyncClient(timeout=60, transport=transport) as client:
        for attempt in range(attempts):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
            except httpx2.HTTPError:
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(wait_s)
    raise AssertionError("unreachable")
