"""A picture per vocabulary word: the scene the generator wrote for it, drawn by
the configured painter and kept in the images folder. The learner describes the
picture with the word in Practice."""

import logging
from pathlib import Path

from app.models import SessionContent, VocabularyItem
from app.painters import Painter

log = logging.getLogger(__name__)

STYLE = "Flat vector illustration, soft colours, simple shapes, one clear scene. No text, letters, numbers, or signs anywhere."


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
