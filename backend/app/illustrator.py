"""A picture per vocabulary word: the scene the generator wrote for it, drawn by
an image MCP server signed in with its API key (OpenRouter, or comfy-cloud while
its subscription lasts) and kept in the images folder. The learner describes
the picture with the word in Practice."""

import base64
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from app.mcp_client import McpClient, McpError, payload
from app.models import SessionContent

log = logging.getLogger(__name__)

# Picture styles the learner can pick in Settings; the key is the setting value.
# A realistic photo gives the most to describe; flat vector was too bare for a sentence.
STYLES: dict[str, str] = {
    "photo": "A realistic photograph, natural light, everyday detail, eye-level view.",
    "cinematic": "A cinematic film still, dramatic lighting, shallow depth of field, rich detail.",
    "storybook": "A warm children's storybook illustration, watercolour and ink, gentle detail.",
    "comic": "A single comic-book panel, bold ink lines, expressive characters, no speech bubbles.",
    "sketch": "A pencil sketch with light shading, loose but clear lines.",
    "flat": "Flat vector illustration, soft colours, simple shapes.",
}
STYLE_LABELS: dict[str, str] = {
    "photo": "realistic photo, the most detail to describe",
    "cinematic": "film still, dramatic light",
    "storybook": "watercolour storybook",
    "comic": "one comic panel",
    "sketch": "pencil sketch",
    "flat": "flat vector, simple shapes",
}
# On every style: the learner has to supply the word, so the picture must not.
NO_TEXT = "One clear scene. No text, letters, numbers, signs, or captions anywhere in the image."
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


class Illustrator:
    def __init__(self, painter: Painter, image_dir: Path, style: str = "photo") -> None:
        self._painter = painter
        self._dir = image_dir
        self._style = STYLES.get(style, STYLES["photo"])

    def prompt(self, scene: str) -> str:
        return f"{self._style} {NO_TEXT} {scene}"

    def illustrate(self, job_id: str, content: SessionContent) -> SessionContent:
        """The content with a picture on every word whose scene got drawn. A word
        without a scene, or whose picture failed, stays as it is."""
        drawable = [(i, item) for i, item in enumerate(content.vocabulary) if item.scene]
        pictures = self._painter.paint([self.prompt(item.scene or "") for _, item in drawable])
        self._dir.mkdir(parents=True, exist_ok=True)
        vocabulary = list(content.vocabulary)
        for (i, item), png in zip(drawable, pictures):
            if png is None:
                log.warning("job %s: no picture for %r", job_id, item.word)
                continue
            name = f"{job_id}-{i}.png"
            (self._dir / name).write_bytes(png)
            vocabulary[i] = item.model_copy(update={"image": name})
        return content.model_copy(update={"vocabulary": vocabulary})
