"""A picture per vocabulary word: the scene the generator wrote for it, drawn by
a painter and kept in the images folder. The learner describes the picture
with the word in Practice."""

import logging
import uuid
from pathlib import Path

from app.llm import GenerationError
from app.models import SessionContent, VocabularyItem
from app.pictures.painters import OnDrawn, Painter
from app.pictures.scenes import Scene

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


class Illustrator:
    def __init__(self, painter: Painter, image_dir: Path, style: str = "photo") -> None:
        self._painter = painter
        self._dir = image_dir
        self._style = STYLES.get(style, STYLES["photo"])

    def expected_seconds(self, count: int) -> float | None:
        """How long `count` pictures usually take with the configured model; None until it drew one here."""
        return self._painter.expected_seconds(count)

    def prompt(self, scene: str, style: str = "") -> str:
        """`style` is a STYLES key to draw this one in; blank means the configured style."""
        return f"{STYLES.get(style, self._style)} {IMAGE_RULES} {scene}"

    def illustrate(self, job_id: str, content: SessionContent, on_drawn: OnDrawn | None = None) -> SessionContent:
        """The content with a picture on every word whose scene got drawn. A word
        without a scene, or whose picture failed, stays as it is."""
        drawable = [(i, item) for i, item in enumerate(content.vocabulary) if item.scene]
        pictures = self._painter.paint([self.prompt(item.scene or "") for _, item in drawable], on_drawn)
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

    def redraw(self, session_id: int, index: int, item: VocabularyItem, scene: Scene, style: str = "") -> VocabularyItem:
        """The item with `scene` (and its caption) drawn in `style` under a new file name. The old file stays until
        the caller has stored the new name and calls `discard` on whatever name it replaced.
        Raises GenerationError when no picture came back."""
        [png] = self._painter.paint([self.prompt(scene.text, style)])
        if png is None:
            raise GenerationError("no picture came back")
        self._dir.mkdir(parents=True, exist_ok=True)
        name = f"{session_id}-{index}-{uuid.uuid4().hex[:8]}.png"
        (self._dir / name).write_bytes(png)
        return item.model_copy(update={"scene": scene.text, "caption": scene.caption or None, "image": name})

    def discard(self, image: str | None) -> None:
        if image:
            (self._dir / image).unlink(missing_ok=True)
