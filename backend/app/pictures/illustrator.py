"""Two pictures per vocabulary word, drawn by a painter and kept in the images
folder: its example sentence, which the card opens on, and the scene the
generator wrote for it, which the learner describes with the word in Practice."""

import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from app.llm import GenerationError
from app.models import SessionContent, VocabularyItem
from app.pictures.painters import OnDrawn, Painter
from app.pictures.scenes import Scene

log = logging.getLogger(__name__)

PictureField = Literal["image", "example_image"]
OnPicture = Callable[[int, PictureField, str], None]  # the word's index, the field the picture fills, its file name

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
    "A landscape picture, 4:3. One coherent scene, rich in detail: a foreground, a background, several people or objects, "
    "and small props a viewer could point at. "
    "No text, letters, numbers, signs, or captions anywhere in the image."
)
# The example picture shows the sentence the card prints under it.
EXAMPLE_SCENE = 'This sentence as one moment: "{example}" In it, "{word}" ({pos}) means: {definition}.'


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

    def example_prompt(self, item: VocabularyItem, style: str = "") -> str:
        scene = EXAMPLE_SCENE.format(example=item.example, word=item.word, pos=item.pos, definition=item.definition)
        return self.prompt(scene, style)

    def _wanted(self, content: SessionContent) -> list[tuple[int, str, str]]:
        """Every picture the content calls for, as (word index, the field it fills, its prompt)."""
        wanted = []
        for i, item in enumerate(content.vocabulary):
            wanted.append((i, "example_image", self.example_prompt(item)))
            if item.scene:
                wanted.append((i, "image", self.prompt(item.scene)))
        return wanted

    def count(self, content: SessionContent) -> int:
        return len(self._wanted(content))

    def illustrate(
        self, job_id: str, content: SessionContent, on_drawn: OnDrawn | None = None, on_picture: OnPicture | None = None
    ) -> SessionContent:
        """The content with the pictures that got drawn: the example on every word, the scene
        on every word that has one. A picture that failed leaves its field as it is.
        `on_picture` hears of each picture as soon as its file is there."""
        wanted = self._wanted(content)
        vocabulary = list(content.vocabulary)
        self._dir.mkdir(parents=True, exist_ok=True)

        def keep(n: int, png: bytes) -> None:
            i, field, _ = wanted[n]
            name = f"{job_id}-{i}{'-example' if field == 'example_image' else ''}.png"
            (self._dir / name).write_bytes(png)
            vocabulary[i] = vocabulary[i].model_copy(update={field: name})
            if on_picture:
                on_picture(i, field, name)

        pictures = self._painter.paint([prompt for _, _, prompt in wanted], on_drawn, keep)
        for (i, field, _), png in zip(wanted, pictures):
            if png is None:
                log.warning("job %s: no %s for %r", job_id, field, vocabulary[i].word)
        return content.model_copy(update={"vocabulary": vocabulary})

    def redraw(self, session_id: int, index: int, item: VocabularyItem, scene: Scene, style: str = "") -> VocabularyItem:
        """The item with `scene` (and its caption) drawn in `style` under a new file name. The old file stays until
        the caller has stored the new name and calls `discard` on whatever name it replaced.
        Raises GenerationError when no picture came back."""
        name = self._draw(self.prompt(scene.text, style), session_id, index)
        return item.model_copy(update={"scene": scene.text, "caption": scene.caption or None, "image": name})

    def redraw_example(self, session_id: int, index: int, item: VocabularyItem, style: str = "") -> VocabularyItem:
        """The item with its example sentence drawn again in `style`; the old file is the caller's to `discard`."""
        return item.model_copy(update={"example_image": self._draw(self.example_prompt(item, style), session_id, index)})

    def _draw(self, prompt: str, session_id: int, index: int) -> str:
        [png] = self._painter.paint([prompt])
        if png is None:
            raise GenerationError("no picture came back")
        self._dir.mkdir(parents=True, exist_ok=True)
        name = f"{session_id}-{index}-{uuid.uuid4().hex[:8]}.png"
        (self._dir / name).write_bytes(png)
        return name

    def discard(self, image: str | None) -> None:
        if image:
            (self._dir / image).unlink(missing_ok=True)
