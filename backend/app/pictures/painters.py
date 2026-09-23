"""Image MCP servers that turn prompts into PNG bytes, signed in with the provider's API key."""

import base64
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from app.mcp_client import McpClient, McpError, payload

log = logging.getLogger(__name__)

OPENROUTER_MCP = "https://mcp.openrouter.ai/mcp"
COMFY_MCP = "https://cloud.comfy.org/mcp"
# Provider -> default image model, Nano Banana Pro on both.
DEFAULT_MODEL = {"openrouter": "google/gemini-3-pro-image", "comfy": "vertexai/nano-banana-pro"}
# Pictures drawn at once; the session has ten words.
PARALLEL = 10


class Painter(Protocol):
    def paint(self, prompts: list[str]) -> list[bytes | None]: ...


def painter_for(provider: str, model: str, keys: dict[str, str]) -> Painter | None:
    """The painter for `provider` ("openrouter" / "comfy"), or None when it is off or its key is missing."""
    key = keys.get(provider, "")
    if provider not in DEFAULT_MODEL or not key:
        return None
    model = model or DEFAULT_MODEL[provider]
    if provider == "comfy":
        return ComfyPainter(McpClient(COMFY_MCP, key), model)
    return OpenRouterPainter(McpClient(OPENROUTER_MCP, key), model)


class OpenRouterPainter:
    """One generate-image call per picture, all in flight at once; the PNG comes back inline as base64."""

    def __init__(self, client: McpClient, model: str) -> None:
        self._client = client
        self._model = model

    def paint(self, prompts: list[str]) -> list[bytes | None]:
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            return list(pool.map(self._one, prompts))

    def _one(self, prompt: str) -> bytes | None:
        try:
            result = self._client.call("generate-image", {"prompt": prompt, "model": self._model})
        except McpError as e:
            log.warning("openrouter could not draw a picture: %s", e)
            return None
        for block in result.get("content", []):
            if block.get("type") == "image" and block.get("data"):
                return base64.b64decode(block["data"])
        log.warning("openrouter returned no image block")
        return None


class ComfyPainter:
    """One batch for all the pictures (comfy draws them side by side), waited on, then the signed URLs fetched at once."""

    WAIT_ROUNDS = 20  # wait_for_batch returns after ~25 s each; about 8 minutes in all

    def __init__(self, client: McpClient, model: str, fetch=None) -> None:
        self._client = client
        self._model = model
        self._fetch = fetch or fetch_url

    def paint(self, prompts: list[str]) -> list[bytes | None]:
        items = [
            {"tool": "partner_generate", "type": "image", "aspect_ratio": "4:3", "prompt": p, "description": f"word {i}", **self._model_fields()}
            for i, p in enumerate(prompts)
        ]
        try:
            submitted = payload(self._client.call("submit_batch", {"client_os": "linux", "confirm": True, "items": items}))
            batch_id, job_ids = submitted["batch_id"], submitted["job_ids"]
            for _ in range(self.WAIT_ROUNDS):
                if not payload(self._client.call("wait_for_batch", {"batch_id": batch_id})).get("timed_out"):
                    break
            outputs = payload(self._client.call("get_batch_output", {"batch_id": batch_id, "client_os": "linux"}))
        except (McpError, KeyError, TypeError) as e:
            log.warning("comfy could not draw the pictures: %s", e)
            return [None] * len(prompts)
        url_of = {o["job_id"]: o["url"] for o in outputs.get("outputs", []) if o.get("url")}
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            return list(pool.map(self._fetch_or_none, [url_of.get(job) for job in job_ids]))

    def _model_fields(self) -> dict:
        """comfy names every OpenAI image model `openai/images-generations` and takes the variant
        in params, so `openai/gpt-image-2.5-flare` (OpenRouter's spelling) works on both providers."""
        if self._model.startswith("openai/gpt-image"):
            return {"model": "openai/images-generations", "params": {"model": self._model.removeprefix("openai/")}}
        return {"model": self._model}

    def _fetch_or_none(self, url: str | None) -> bytes | None:
        if not url:
            return None
        try:
            return self._fetch(url)
        except (OSError, ValueError) as e:
            log.warning("could not fetch a picture from %s: %s", url, e)
            return None


def fetch_url(url: str, attempts: int = 3) -> bytes:
    """The bytes at `url`; the signed links flake, so a failed try is repeated after a short wait."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except (OSError, ValueError):
            if attempt == attempts - 1:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")
