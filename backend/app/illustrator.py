"""A picture per vocabulary word: the scene the generator wrote for it, drawn by
OpenRouter's MCP server (`generate-image`, signed in with the API key) and kept
in the images folder. The learner describes the picture with the word in Practice."""

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from app.mcp_client import McpClient, McpError
from app.models import SessionContent

log = logging.getLogger(__name__)

STYLE = "Flat vector illustration, soft colours, simple shapes, one clear scene. No text, letters, numbers, or signs anywhere."
OPENROUTER_MCP = "https://mcp.openrouter.ai/mcp"
# Pictures drawn at once; the session has ten words.
PARALLEL = 10


class Painter(Protocol):
    def paint(self, prompts: list[str]) -> list[bytes | None]: ...


class OpenRouterPainter:
    """One generate-image call per picture, all in flight at once; the PNG comes back inline as base64."""

    def __init__(self, client: McpClient, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def with_key(cls, api_key: str, model: str) -> "OpenRouterPainter":
        return cls(McpClient(OPENROUTER_MCP, api_key), model)

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


class Illustrator:
    def __init__(self, painter: Painter, image_dir: Path) -> None:
        self._painter = painter
        self._dir = image_dir

    def illustrate(self, job_id: str, content: SessionContent) -> SessionContent:
        """The content with a picture on every word whose scene got drawn. A word
        without a scene, or whose picture failed, stays as it is."""
        drawable = [(i, item) for i, item in enumerate(content.vocabulary) if item.scene]
        pictures = self._painter.paint([f"{STYLE} {item.scene}" for _, item in drawable])
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
