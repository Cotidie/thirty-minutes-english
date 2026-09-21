"""A picture per vocabulary word: the scene the generator wrote for it, drawn by
an image MCP server signed in with its API key (OpenRouter, or comfy-cloud while
its subscription lasts) and kept in the images folder. The learner describes
the picture with the word in Practice."""

import base64
import logging
import random
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.claude_cli import ClaudeCli, GenerationError, structured_output
from app.mcp_client import McpClient, McpError, payload
from app.models import SessionContent, VocabularyItem

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
    "photo": "realistic photo",
    "cinematic": "film still",
    "storybook": "watercolour storybook",
    "comic": "comic panel",
    "sketch": "pencil sketch",
    "flat": "flat vector",
}
# On every style: plenty to point at, and the learner has to supply the word, so the picture must not.
IMAGE_RULES = (
    "One coherent scene, rich in detail: a foreground, a background, several people or objects, "
    "and small props a viewer could point at. "
    "No text, letters, numbers, signs, or captions anywhere in the image."
)
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


# What a scene is, for the session generator and the redraw writer alike.
SCENE_RULES = """two or three sentences describing one drawable moment where a fluent speaker would reach \
for the word, so that a learner shown a picture of it would describe it with the word. Name the place, who \
is there and what they are doing, and three or four supporting details a viewer could point at: objects, \
weather, time of day, what is going on in the background. Physical and specific ("a single toll booth open \
on a wide highway at dusk, a line of cars backed up behind it, a driver leaning out of a window, a cyclist \
slipping past on the shoulder"), never abstract, and nothing that needs written words in the picture"""

SCENE_SCHEMA: dict = {"type": "object", "additionalProperties": False, "required": ["scene"], "properties": {"scene": {"type": "string"}}}

SCENE_PROMPT = """A learner will be shown a picture and asked to describe it in one sentence using this word:

Word: {word} ({pos})
Meaning: {definition}
Example: {example}

Write a new scene for the picture: {rules}.

Start from this spark and build the scene around it; swap any part that does not fit the word, but keep \
its flavour so the scene is fresh: {spark}.
It must differ clearly from this earlier scene, which the learner has already seen: {previous}

Return only the structured output."""

# Rolled per redraw so the writer, which otherwise settles on its favourite scene
# for a word, starts somewhere new each time.
PLACES = (
    "a crowded family kitchen", "a factory floor between shifts", "a hospital corridor", "an open-plan office",
    "a street market", "a train platform", "a school classroom", "a construction site", "a farm at harvest",
    "a small repair shop", "an airport gate", "a living room during a party", "a city park on a weekend",
    "a fishing harbour", "a laboratory bench", "a mountain trail", "a supermarket checkout", "a football pitch",
    "a hotel lobby", "a rooftop", "a courtroom", "a wedding hall", "a bus stuck in traffic", "a night market",
    "a village square", "a shipping warehouse", "a dentist's waiting room", "a campsite", "a subway car", "a bakery at opening time",
)
MOMENTS = (
    "early morning light", "pouring rain", "late at night under artificial light", "a heatwave afternoon",
    "the first snow of the year", "golden hour", "a power cut", "the minute before a deadline", "a public holiday",
    "thick fog", "the middle of a storm", "the last hour before closing",
)
TWISTS = (
    "a child watching closely", "a dog getting in the way", "something has just gone wrong", "someone in a hurry",
    "a crowd looking on", "an old and a new version side by side", "an elderly person and a teenager together",
    "a visitor who does not belong there", "a phone held up, filming", "far too many of one thing",
    "one person doing the job of three", "a celebration nobody expected",
)


@dataclass(frozen=True)
class Spark:
    """A random starting point for a scene: where, when, and one thing that makes it a story."""

    place: str
    moment: str
    twist: str

    @classmethod
    def roll(cls, rng: random.Random) -> "Spark":
        return cls(rng.choice(PLACES), rng.choice(MOMENTS), rng.choice(TWISTS))

    def __str__(self) -> str:
        return f"place: {self.place}; moment: {self.moment}; twist: {self.twist}"


class Runner(Protocol):
    def run(self, prompt: str, schema: dict, on_event=None) -> dict: ...


class SceneWriter:
    """A fresh scene for one word, from a short text run of the claude CLI seeded with a random Spark."""

    def __init__(self, cli: Runner, rng: random.Random | None = None) -> None:
        self._cli = cli
        self._rng = rng or random.Random()

    @classmethod
    def with_cli(cls, model: str) -> "SceneWriter":
        return cls(ClaudeCli(model=model, effort="low", tools=(), mcp=None, timeout_s=60))

    def build_prompt(self, item: VocabularyItem, spark: Spark) -> str:
        return SCENE_PROMPT.format(
            word=item.word, pos=item.pos, definition=item.definition, example=item.example,
            rules=SCENE_RULES, spark=spark, previous=item.scene or "none",
        )

    def write(self, item: VocabularyItem) -> str:
        """Raises GenerationError when the run fails or comes back blank."""
        prompt = self.build_prompt(item, Spark.roll(self._rng))
        scene = str(structured_output(self._cli.run(prompt, SCENE_SCHEMA)).get("scene", "")).strip()
        if not scene:
            raise GenerationError("the model wrote no scene")
        return scene


class Illustrator:
    def __init__(self, painter: Painter, image_dir: Path, style: str = "photo") -> None:
        self._painter = painter
        self._dir = image_dir
        self._style = STYLES.get(style, STYLES["photo"])

    def prompt(self, scene: str, style: str = "") -> str:
        """`style` is a STYLES key to draw this one in; blank means the configured style."""
        return f"{STYLES.get(style, self._style)} {IMAGE_RULES} {scene}"

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

    def redraw(self, session_id: int, index: int, item: VocabularyItem, scene: str, style: str = "") -> VocabularyItem:
        """The item with `scene` drawn in `style` under a new file name. The old file stays until
        the caller has stored the new name and calls `discard` on whatever name it replaced.
        Raises GenerationError when no picture came back."""
        [png] = self._painter.paint([self.prompt(scene, style)])
        if png is None:
            raise GenerationError("no picture came back")
        self._dir.mkdir(parents=True, exist_ok=True)
        name = f"{session_id}-{index}-{uuid.uuid4().hex[:8]}.png"
        (self._dir / name).write_bytes(png)
        return item.model_copy(update={"scene": scene, "image": name})

    def discard(self, image: str | None) -> None:
        if image:
            (self._dir / image).unlink(missing_ok=True)
