"""Images the generator saw on the pages it drew the article from, downloaded and kept like any
other picture: a pictures row, and its file images/{id}.png."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from io import BytesIO
from typing import TYPE_CHECKING

import httpx2
from PIL import Image

from app.pictures.files import PictureFiles
from app.pictures.painters import fetch_url

if TYPE_CHECKING:
    from app.db.pictures import PictureRepo

log = logging.getLogger(__name__)

MIN_SIDE = 300  # anything smaller is a logo, an icon, or a thumbnail
MAX_SIDE = 1600  # enough for the article column; a 6000px original would only cost disk


def as_png(data: bytes) -> bytes | None:
    """The image as a PNG no larger than MAX_SIDE; None when it is not a picture worth showing."""
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            if min(source.size) < MIN_SIDE:
                return None
            picture = source.convert("RGBA" if "A" in source.getbands() else "RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    picture.thumbnail((MAX_SIDE, MAX_SIDE))
    out = BytesIO()
    picture.save(out, "PNG", optimize=True)
    return out.getvalue()


class SourceImages:
    def __init__(self, pictures: "PictureRepo", files: PictureFiles, fetch: Callable[[str], Awaitable[bytes]] = fetch_url) -> None:
        self._pictures = pictures
        self._files = files
        self._fetch = fetch

    def keep(self, url: str) -> int | None:
        """The new picture's id, or None (logged) when the image will not download or is not a picture."""
        try:
            data = asyncio.run(self._fetch(url))
        except httpx2.HTTPError as e:
            log.warning("could not download %s: %s", url, e)
            return None
        png = as_png(data)
        if png is None:
            log.info("skipped %s: not a picture, or too small to be one", url)
            return None
        picture_id = self._pictures.add(None, None, None)
        self._files.write(picture_id, png)
        return picture_id

    def drop(self, picture_id: int) -> None:
        self._files.remove(picture_id)
