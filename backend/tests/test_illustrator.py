import pytest

from app.claude_cli import GenerationError
from app.illustrator import Illustrator
from tests.conftest import sample_content


class FakeCli:
    def __init__(self, pictures=None, error: Exception | None = None):
        self.pictures = pictures
        self.error = error
        self.prompt = ""

    def run(self, prompt: str, schema: dict, on_event=None) -> dict:
        self.prompt = prompt
        if self.error:
            raise self.error
        return {"structured_output": {"pictures": self.pictures}}


def picture(i: int) -> dict:
    return {"word": f"word{i}", "scene": f"scene {i}", "url": f"https://img/{i}"}


def fetch(url: str) -> bytes:
    if url.endswith("/3"):
        raise OSError("gone")
    return b"PNG" + url.encode()


def test_every_word_gets_its_scene_and_picture_file(tmp_path):
    content = sample_content()
    cli = FakeCli([picture(i) for i in range(len(content.vocabulary))])
    done = Illustrator(cli, tmp_path / "images", "vertexai/nano-banana-2-lite", fetch=lambda u: b"PNG").illustrate("job1", content)

    assert [v.image for v in done.vocabulary] == [f"job1-{i}.png" for i in range(len(content.vocabulary))]
    assert done.vocabulary[2].scene == "scene 2"
    assert (tmp_path / "images" / "job1-0.png").read_bytes() == b"PNG"
    assert content.vocabulary[0].image is None  # the input is untouched
    assert "- word0 (noun): def 0. Example: ex 0" in cli.prompt
    assert 'model "vertexai/nano-banana-2-lite"' in cli.prompt
    assert "confirm: true" in cli.prompt


def test_a_word_without_a_picture_or_with_a_dead_link_stays_bare(tmp_path):
    content = sample_content()
    pictures = [picture(i) for i in range(len(content.vocabulary)) if i != 1]
    pictures[0]["word"] = " Word0 "  # matched case-insensitively, trimmed
    done = Illustrator(FakeCli(pictures), tmp_path, "m", fetch=fetch).illustrate("j", content)

    assert done.vocabulary[0].image == "j-0.png"
    assert done.vocabulary[1].image is None and done.vocabulary[1].scene is None
    assert done.vocabulary[3].image is None and done.vocabulary[3].scene == "scene 3"
    assert not (tmp_path / "j-3.png").exists()


def test_a_failed_run_raises(tmp_path):
    with pytest.raises(GenerationError):
        Illustrator(FakeCli(error=GenerationError("boom")), tmp_path, "m").illustrate("j", sample_content())


def test_fetch_retries_a_flaky_link(monkeypatch):
    import app.illustrator as mod

    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"PNG"

    def urlopen(url, timeout):
        calls.append(url)
        if calls.count(url) < 3:
            raise OSError("wrong version number")
        return Response()

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    assert mod.fetch_url("https://img/1") == b"PNG"
    assert calls == ["https://img/1"] * 3
    with pytest.raises(OSError):
        mod.fetch_url("https://img/2", attempts=2)
