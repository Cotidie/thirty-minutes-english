"""Who draws the pictures: an MCP server the host has logged in to. Each painter
takes one prompt per picture and returns the PNG bytes, or None where that one
failed. The comfy-cloud subscription runs out first; OpenRouter is its successor."""

import base64
import logging
import time
import urllib.request
from typing import Protocol

from app.mcp_client import McpClient, McpError, oauth_token, payload

log = logging.getLogger(__name__)

COMFY_URL = "https://cloud.comfy.org/mcp"
OPENROUTER_URL = "https://mcp.openrouter.ai/mcp"

# Provider name -> (MCP url, default image model on it). Nano Banana Pro on both.
PROVIDERS: dict[str, tuple[str, str]] = {
    "comfy": (COMFY_URL, "vertexai/nano-banana-pro"),
    "openrouter": (OPENROUTER_URL, "google/gemini-3-pro-image"),
}


class Painter(Protocol):
    def paint(self, prompts: list[str]) -> list[bytes | None]: ...


def painter_for(provider: str, model: str) -> Painter | None:
    """The painter for a provider name, or None when the host has no login for it."""
    if provider not in PROVIDERS:
        return None
    url, default_model = PROVIDERS[provider]
    token = oauth_token(url)
    if not token:
        log.warning("no OAuth login for %s (%s): run `claude mcp login` on the host", provider, url)
        return None
    client = McpClient(url, token)
    model = model or default_model
    return ComfyPainter(client, model) if provider == "comfy" else OpenRouterPainter(client, model)


class ComfyPainter:
    """One batch for all the pictures, waited on, then each signed URL fetched."""

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
        submitted = payload(self._client.call("submit_batch", {"client_os": "linux", "confirm": True, "items": items}))
        batch_id, job_ids = submitted["batch_id"], submitted["job_ids"]
        for _ in range(self.WAIT_ROUNDS):
            if not payload(self._client.call("wait_for_batch", {"batch_id": batch_id})).get("timed_out"):
                break
        outputs = payload(self._client.call("get_batch_output", {"batch_id": batch_id, "client_os": "linux"}))
        url_of = {o["job_id"]: o["url"] for o in outputs.get("outputs", []) if o.get("url")}
        return [self._fetch_or_none(url_of.get(job)) for job in job_ids]

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


class OpenRouterPainter:
    """One generate-image call per picture; the PNG comes back inline as base64."""

    def __init__(self, client: McpClient, model: str) -> None:
        self._client = client
        self._model = model

    def paint(self, prompts: list[str]) -> list[bytes | None]:
        return [self._one(p) for p in prompts]

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
