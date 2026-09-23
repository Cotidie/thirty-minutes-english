"""Image MCP servers that turn prompts into PNG bytes, signed in with the provider's API key."""

import asyncio
import base64
import logging
from collections.abc import Callable
from typing import Protocol

import httpx2

from app.mcp_client import McpError, McpHttp, Session, payload

log = logging.getLogger(__name__)

OPENROUTER_MCP = "https://mcp.openrouter.ai/mcp"
COMFY_MCP = "https://cloud.comfy.org/mcp"
# Provider -> default image model, Nano Banana Pro on both.
DEFAULT_MODEL = {"openrouter": "google/gemini-3-pro-image", "comfy": "vertexai/nano-banana-pro"}


OnDrawn = Callable[[int], None]  # pictures finished so far; raising from it stops the painter


class Painter(Protocol):
    def paint(self, prompts: list[str], on_drawn: OnDrawn | None = None) -> list[bytes | None]: ...


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


def painter_for(provider: str, model: str, keys: dict[str, str]) -> Painter | None:
    """The painter for `provider` ("openrouter" / "comfy"), or None when it is off or its key is missing."""
    key = keys.get(provider, "")
    if provider not in DEFAULT_MODEL or not key:
        return None
    model = model or DEFAULT_MODEL[provider]
    if provider == "comfy":
        return ComfyPainter(McpHttp(COMFY_MCP, key), model)
    return OpenRouterPainter(McpHttp(OPENROUTER_MCP, key), model)


class OpenRouterPainter:
    """One generate-image call per picture, all in flight on one session; the PNG comes back inline as base64."""

    def __init__(self, server: McpHttp, model: str) -> None:
        self._server = server
        self._model = model

    def paint(self, prompts: list[str], on_drawn: OnDrawn | None = None) -> list[bytes | None]:
        return asyncio.run(self._paint(prompts, Counter(on_drawn)))

    async def _paint(self, prompts: list[str], counter: Counter) -> list[bytes | None]:
        async def one(session: Session, prompt: str) -> bytes | None:
            png = await self._one(session, prompt)
            counter.tick()
            return png

        try:
            async with self._server.session() as session:
                return list(await asyncio.gather(*(one(session, p) for p in prompts)))
        except McpError as e:
            log.warning("openrouter could not draw the pictures: %s", e)
            return [None] * len(prompts)

    async def _one(self, session: Session, prompt: str) -> bytes | None:
        try:
            result = await session.call("generate-image", {"prompt": prompt, "model": self._model})
        except McpError as e:
            log.warning("openrouter could not draw a picture: %s", e)
            return None
        for block in result.content:
            if block.type == "image" and block.data:
                return base64.b64decode(block.data)
        log.warning("openrouter returned no image block")
        return None


class ComfyPainter:
    """One batch for all the pictures (comfy draws them side by side), waited on, then the signed URLs fetched at once."""

    WAIT_ROUNDS = 20  # wait_for_batch returns after ~25 s each; about 8 minutes in all

    def __init__(self, server: McpHttp, model: str, fetch=None) -> None:
        self._server = server
        self._model = model
        self._fetch = fetch or fetch_url

    def paint(self, prompts: list[str], on_drawn: OnDrawn | None = None) -> list[bytes | None]:
        return asyncio.run(self._paint(prompts, Counter(on_drawn)))

    async def _paint(self, prompts: list[str], counter: Counter) -> list[bytes | None]:
        items = [
            {"tool": "partner_generate", "type": "image", "aspect_ratio": "4:3", "prompt": p, "description": f"word {i}", **self._model_fields()}
            for i, p in enumerate(prompts)
        ]
        try:
            async with self._server.session() as session:
                submitted = payload(await session.call("submit_batch", {"client_os": "linux", "confirm": True, "items": items}))
                batch_id, job_ids = submitted["batch_id"], submitted["job_ids"]
                for _ in range(self.WAIT_ROUNDS):
                    waited = payload(await session.call("wait_for_batch", {"batch_id": batch_id}))
                    counter.reach(finished(waited))
                    if not waited.get("timed_out"):
                        break
                outputs = payload(await session.call("get_batch_output", {"batch_id": batch_id, "client_os": "linux"}))
        except (McpError, KeyError, TypeError) as e:
            log.warning("comfy could not draw the pictures: %s", e)
            return [None] * len(prompts)
        url_of = {o["job_id"]: o["url"] for o in outputs.get("outputs", []) if o.get("url")}
        return list(await asyncio.gather(*(self._fetch_or_none(url_of.get(job)) for job in job_ids)))

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
