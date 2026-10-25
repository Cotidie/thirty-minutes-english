"""The picture files: picture {id} is images/{id}.png. The illustrator writes them; deleting a
session or redrawing a word removes the ones nobody shows any more."""

from pathlib import Path


class PictureFiles:
    def __init__(self, dir: Path) -> None:
        self.dir = Path(dir)

    @staticmethod
    def name(picture_id: int) -> str:
        return f"{picture_id}.png"

    def path(self, picture_id: int) -> Path:
        return self.dir / self.name(picture_id)

    def write(self, picture_id: int, png: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path(picture_id).write_bytes(png)

    def remove(self, picture_id: int | None) -> None:
        if picture_id is not None:
            self.path(picture_id).unlink(missing_ok=True)
