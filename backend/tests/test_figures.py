import asyncio
from io import BytesIO

import httpx2
import pytest
from PIL import Image

from app.db import Database
from app.pictures.figures import MAX_SIDE, SourceImages, as_png, fetch_url
from app.pictures.files import PictureFiles


def image(width: int, height: int, fmt: str = "JPEG") -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), (200, 120, 40)).save(out, fmt)
    return out.getvalue()


def test_a_photo_is_kept_as_a_png_no_larger_than_the_cap():
    png = as_png(image(3200, 1800))
    with Image.open(BytesIO(png)) as kept:
        assert kept.format == "PNG" and max(kept.size) == MAX_SIDE and kept.size == (MAX_SIDE, 900)


def test_icons_and_things_that_are_not_pictures_are_refused():
    assert as_png(image(120, 120, "PNG")) is None  # a logo or an icon
    assert as_png(b"<svg></svg>") is None
    assert as_png(b"") is None


def sources_over(tmp_path, answer) -> tuple[SourceImages, Database, PictureFiles]:
    db = Database(tmp_path / "s.db")
    files = PictureFiles(tmp_path / "images")

    async def fetch(url):
        return answer(url)

    return SourceImages(db.pictures, files, fetch), db, files


def test_a_source_image_becomes_a_picture_row_and_its_file(tmp_path):
    sources, db, files = sources_over(tmp_path, lambda url: image(800, 600))
    picture = sources.keep("https://news.example/tram.jpg")
    assert files.path(picture).read_bytes().startswith(b"\x89PNG")
    assert db.pictures.stats() == {}  # not drawn here, so it says nothing about a model's time


def test_an_image_that_will_not_download_or_open_is_skipped(tmp_path):
    def refuse(url):
        raise httpx2.ConnectError("gone")

    assert sources_over(tmp_path, refuse)[0].keep("https://gone.example/a.jpg") is None
    sources, _, files = sources_over(tmp_path, lambda url: b"not an image")
    assert sources.keep("https://x.example/a.jpg") is None and not files.dir.exists()


def test_fetch_gets_past_a_host_that_refuses_the_http_librarys_own_name():
    def wikimedia(request):
        refused = request.headers["user-agent"].startswith("python-")
        return httpx2.Response(403 if refused else 200, content=b"PNG")

    transport = httpx2.MockTransport(wikimedia)
    assert asyncio.run(fetch_url("https://upload.wikimedia.org/a.png", attempts=1, wait_s=0, transport=transport)) == b"PNG"


def test_fetch_retries_a_flaky_link():
    calls = []

    def answer(request):
        calls.append(str(request.url))
        if calls.count(str(request.url)) < 3:
            return httpx2.Response(502)
        return httpx2.Response(200, content=b"PNG")

    transport = httpx2.MockTransport(answer)
    assert asyncio.run(fetch_url("https://img/1", wait_s=0, transport=transport)) == b"PNG"
    assert calls == ["https://img/1"] * 3
    with pytest.raises(httpx2.HTTPError):
        asyncio.run(fetch_url("https://img/2", attempts=2, wait_s=0, transport=transport))
