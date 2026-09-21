"""A picture per vocabulary word: a situation the word fits, drawn through the
comfy-cloud MCP by one run of the claude CLI, then downloaded into the images
folder. The learner describes the picture with the word in Practice."""

import logging
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.claude_cli import COMFY, ClaudeCli, GenerationError, structured_output
from app.models import SessionContent

log = logging.getLogger(__name__)

PICTURES_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pictures"],
    "properties": {
        "pictures": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["word", "scene", "url"],
                "properties": {
                    "word": {"type": "string"},
                    "scene": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
        }
    },
}

PROMPT = """Draw one picture per vocabulary word for a pair of adult English learners. In Practice the \
learner looks at the picture and describes it in one sentence that uses the word, so each picture must \
show a situation the word fits without showing the word itself.

Words:
{words}

For each word write a scene: one sentence naming a concrete situation, place, or object where a \
fluent speaker would reach for this word, chosen so the word is the natural way to describe what is \
shown. Then turn each scene into an image prompt: "{style}" followed by the scene. The image must \
contain no text, letters, numbers, signs, or captions of any kind.

Generate all pictures in ONE call to mcp__comfy-cloud__submit_batch with confirm: true and \
client_os: "linux". Each item: tool "partner_generate", type "image", model "{model}", \
aspect_ratio "4:3", prompt as above, description = the word. Then call mcp__comfy-cloud__wait_for_batch \
until it is no longer in progress (call it again when it times out), then \
mcp__comfy-cloud__get_batch_output with client_os: "linux".

Return one entry per word with its scene and the picture's download URL exactly as given. Leave out a \
word whose picture failed. Return only the structured output."""

STYLE = "Flat vector illustration, soft colours, simple shapes, one clear scene, no text anywhere."


class Runner(Protocol):
    def run(self, prompt: str, schema: dict, on_event=None) -> dict: ...


Fetch = Callable[[str], bytes]


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
    def __init__(self, cli: Runner, image_dir: Path, image_model: str, fetch: Fetch = fetch_url) -> None:
        self._cli = cli
        self._dir = image_dir
        self._model = image_model
        self._fetch = fetch

    @classmethod
    def with_cli(cls, image_dir: Path, image_model: str, model: str) -> "Illustrator":
        return cls(ClaudeCli(model=model, effort="low", tools=(), mcp=COMFY, timeout_s=600), image_dir, image_model)

    def build_prompt(self, content: SessionContent) -> str:
        words = "\n".join(f"- {v.word} ({v.pos}): {v.definition}. Example: {v.example}" for v in content.vocabulary)
        return PROMPT.format(words=words, style=STYLE, model=self._model)

    def illustrate(self, job_id: str, content: SessionContent) -> SessionContent:
        """The content with a scene and a picture on every word that got one. Raises
        GenerationError when the run itself fails; a single missing picture is only logged."""
        envelope = self._cli.run(self.build_prompt(content), PICTURES_SCHEMA)
        pictures = {p["word"].strip().lower(): p for p in structured_output(envelope).get("pictures", [])}
        self._dir.mkdir(parents=True, exist_ok=True)
        vocabulary = []
        for i, item in enumerate(content.vocabulary):
            picture = pictures.get(item.word.strip().lower())
            if picture is None:
                log.warning("job %s: no picture came back for %r", job_id, item.word)
                vocabulary.append(item)
                continue
            name = f"{job_id}-{i}.png"
            try:
                (self._dir / name).write_bytes(self._fetch(picture["url"]))
            except (OSError, ValueError) as e:
                log.warning("job %s: could not fetch the picture for %r from %s: %s", job_id, item.word, picture["url"], e)
                vocabulary.append(item.model_copy(update={"scene": picture["scene"]}))
                continue
            vocabulary.append(item.model_copy(update={"scene": picture["scene"], "image": name}))
        return content.model_copy(update={"vocabulary": vocabulary})
