"""Two pictures per vocabulary word, drawn by a painter, each kept as a pictures row and its file:
the example sentence, which the card opens on, and the scene the generator wrote for it, which the
learner describes with the word in Practice."""

import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Literal

from app.llm import GenerationError
from app.models import VocabularyDraft
from app.pictures.files import PictureFiles
from app.pictures.painters import Drawn, OnDrawn, Painter
from app.pictures.scenes import Scene

if TYPE_CHECKING:
    from app.db.pictures import PictureRepo

log = logging.getLogger(__name__)

PictureField = Literal["image", "example_image"]
OnPicture = Callable[[int, PictureField, int], None]  # the word's index, the field the picture fills, its picture id

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
    def __init__(self, painter: Painter, pictures: "PictureRepo", files: PictureFiles, style: str = "photo") -> None:
        self._painter = painter
        self._pictures = pictures
        self._files = files
        self._style = STYLES.get(style, STYLES["photo"])

    def expected_seconds(self, count: int) -> float | None:
        """How long `count` pictures usually take with the configured model; None until it drew one here."""
        return self._painter.expected_seconds(count)

    def prompt(self, scene: str, style: str = "") -> str:
        """`style` is a STYLES key to draw this one in; blank means the configured style."""
        return f"{STYLES.get(style, self._style)} {IMAGE_RULES} {scene}"

    def example_prompt(self, item: VocabularyDraft, style: str = "") -> str:
        scene = EXAMPLE_SCENE.format(example=item.example, word=item.word, pos=item.pos, definition=item.definition)
        return self.prompt(scene, style)

    def _wanted(self, vocabulary: Sequence[VocabularyDraft]) -> list[tuple[int, PictureField, str]]:
        """Every picture the words call for, as (word index, the field it fills, its prompt)."""
        wanted: list[tuple[int, PictureField, str]] = []
        for i, item in enumerate(vocabulary):
            wanted.append((i, "example_image", self.example_prompt(item)))
            if item.scene:
                wanted.append((i, "image", self.prompt(item.scene)))
        return wanted

    def count(self, vocabulary: Sequence[VocabularyDraft]) -> int:
        return len(self._wanted(vocabulary))

    def illustrate(
        self, job_id: str, vocabulary: Sequence[VocabularyDraft], on_drawn: OnDrawn | None = None, on_picture: OnPicture | None = None
    ) -> None:
        """Draws the example of every word and the scene of every word that has one. `on_picture` hears of
        each picture as soon as its row and file are there; a picture that failed is not heard of."""
        wanted = self._wanted(vocabulary)

        def keep(n: int, drawn: Drawn) -> None:
            i, field, _ = wanted[n]
            picture_id = self._keep(drawn)
            if on_picture:
                on_picture(i, field, picture_id)

        pictures = self._painter.paint([prompt for _, _, prompt in wanted], on_drawn, keep)
        for (i, field, _), drawn in zip(wanted, pictures):
            if drawn is None:
                log.warning("job %s: no %s for %r", job_id, field, vocabulary[i].word)

    def redraw(self, scene: Scene, style: str = "") -> int:
        """`scene` drawn in `style`, as a new picture. The old one stays until the caller has stored the new id
        and removes the old file. Raises GenerationError when no picture came back."""
        return self._draw(self.prompt(scene.text, style))

    def redraw_example(self, item: VocabularyDraft, style: str = "") -> int:
        """The word's example sentence drawn again in `style`, as a new picture; the old file is the caller's to remove."""
        return self._draw(self.example_prompt(item, style))

    def _draw(self, prompt: str) -> int:
        [drawn] = self._painter.paint([prompt])
        if drawn is None:
            raise GenerationError("no picture came back")
        return self._keep(drawn)

    def _keep(self, drawn: Drawn) -> int:
        picture_id = self._pictures.add(drawn.model, drawn.seconds, drawn.cost)
        self._files.write(picture_id, drawn.png)
        return picture_id
