import base64
import threading

import json

import pytest

import app.illustrator as mod
from app.claude_cli import GenerationError
from app.illustrator import NO_TEXT, STYLES, ComfyPainter, Illustrator, OpenRouterPainter, SceneWriter, fetch_url, painter_for
from app.mcp_client import McpError
from tests.conftest import sample_content


class FakePainter:
    def __init__(self, blank: set[int] = frozenset()):
        self.blank = blank
        self.prompts: list[str] = []

    def paint(self, prompts: list[str]) -> list[bytes | None]:
        self.prompts = prompts
        return [None if i in self.blank else f"PNG{i}".encode() for i in range(len(prompts))]


def test_every_word_with_a_scene_gets_its_picture_file(tmp_path):
    content = sample_content()
    painter = FakePainter()
    done = Illustrator(painter, tmp_path / "images").illustrate("job1", content)

    assert painter.prompts[0] == f"{STYLES['photo']} {NO_TEXT} scene 0"
    assert [v.image for v in done.vocabulary] == [f"job1-{i}.png" for i in range(len(content.vocabulary))]
    assert (tmp_path / "images" / "job1-2.png").read_bytes() == b"PNG2"
    assert content.vocabulary[0].image is None  # the input is untouched


def test_the_chosen_style_leads_the_prompt_and_an_unknown_one_falls_back_to_photo(tmp_path):
    assert Illustrator(FakePainter(), tmp_path, "comic").prompt("a dog") == f"{STYLES['comic']} {NO_TEXT} a dog"
    assert Illustrator(FakePainter(), tmp_path, "nope").prompt("a dog").startswith(STYLES["photo"])


def test_a_word_without_a_scene_is_skipped_and_a_failed_picture_stays_bare(tmp_path):
    content = sample_content()
    words = list(content.vocabulary)
    words[1] = words[1].model_copy(update={"scene": None})
    content = content.model_copy(update={"vocabulary": words})
    painter = FakePainter(blank={2})  # the third prompt, which is word 3 once word 1 is skipped
    done = Illustrator(painter, tmp_path).illustrate("j", content)

    assert len(painter.prompts) == len(words) - 1
    assert done.vocabulary[0].image == "j-0.png"
    assert done.vocabulary[1].image is None
    assert done.vocabulary[2].image == "j-2.png"
    assert done.vocabulary[3].image is None
    assert not (tmp_path / "j-3.png").exists()


class FakeMcp:
    """Answers generate-image per prompt; the calls come in side by side."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []
        self.lock = threading.Lock()

    def call(self, tool: str, arguments: dict) -> dict:
        with self.lock:
            self.calls.append((tool, arguments))
        answer = self.answers[arguments["prompt"]]
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_openrouter_draws_every_prompt_at_once_and_shrugs_off_a_failed_one():
    png = base64.b64encode(b"PNG-a").decode()
    mcp = FakeMcp({
        "a": {"content": [{"type": "text", "text": "here"}, {"type": "image", "data": png, "mimeType": "image/png"}]},
        "b": McpError("generate-image: over budget"),
        "c": {"content": [{"type": "text", "text": "nothing"}]},
    })
    pictures = OpenRouterPainter(mcp, "google/gemini-3-pro-image").paint(["a", "b", "c"])

    assert pictures == [b"PNG-a", None, None]
    assert sorted(c[1]["prompt"] for c in mcp.calls) == ["a", "b", "c"]
    assert mcp.calls[0] == ("generate-image", {"prompt": mcp.calls[0][1]["prompt"], "model": "google/gemini-3-pro-image"})


class FakeComfy:
    """Answers per tool in order."""

    def __init__(self, results: dict[str, list]):
        self.results = {tool: list(rs) for tool, rs in results.items()}
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, arguments))
        result = self.results[tool].pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def text(data) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


def test_comfy_submits_one_batch_waits_and_fetches_each_job_in_order():
    mcp = FakeComfy({
        "submit_batch": [text({"batch_id": "b1", "job_ids": ["j0", "j1", "j2"]})],
        "wait_for_batch": [text({"timed_out": True}), text({"timed_out": False})],
        "get_batch_output": [text({"outputs": [{"job_id": "j2", "url": "https://x/2"}, {"job_id": "j0", "url": "https://x/0"}]})],
    })
    fetched = []
    lock = threading.Lock()

    def fetch(url):
        with lock:
            fetched.append(url)
        if url.endswith("/2"):
            raise OSError("gone")
        return b"PNG" + url[-1].encode()

    pictures = ComfyPainter(mcp, "vertexai/nano-banana-pro", fetch=fetch).paint(["a", "b", "c"])

    assert pictures == [b"PNG0", None, None]
    submit = mcp.calls[0][1]
    assert submit["confirm"] is True
    assert [i["prompt"] for i in submit["items"]] == ["a", "b", "c"]
    assert submit["items"][0]["model"] == "vertexai/nano-banana-pro"
    assert [c[0] for c in mcp.calls] == ["submit_batch", "wait_for_batch", "wait_for_batch", "get_batch_output"]
    assert sorted(fetched) == ["https://x/0", "https://x/2"]


def test_comfy_spells_an_openai_model_as_the_partner_slug_plus_variant_and_survives_a_refused_batch():
    mcp = FakeComfy({"submit_batch": [McpError("submit_batch: no credits")]})
    assert ComfyPainter(mcp, "openai/gpt-image-2.5-flare").paint(["a", "b"]) == [None, None]
    item = mcp.calls[0][1]["items"][0]
    assert item["model"] == "openai/images-generations"
    assert item["params"] == {"model": "gpt-image-2.5-flare"}


def test_painter_for_picks_the_provider_and_needs_its_key():
    keys = {"openrouter": "sk-or", "comfy": ""}
    assert isinstance(painter_for("openrouter", "", keys), OpenRouterPainter)
    assert painter_for("comfy", "", keys) is None
    assert isinstance(painter_for("comfy", "", {"comfy": "comfyui-1"}), ComfyPainter)
    assert painter_for("off", "", keys) is None


def test_fetch_retries_a_flaky_link(monkeypatch):
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
    assert fetch_url("https://img/1") == b"PNG"
    assert calls == ["https://img/1"] * 3
    with pytest.raises(OSError):
        fetch_url("https://img/2", attempts=2)


def test_redraw_draws_the_new_scene_in_the_asked_style_under_a_new_name_and_drops_the_old_file(tmp_path):
    content = sample_content()
    old = content.vocabulary[2].model_copy(update={"image": "old.png"})
    (tmp_path / "old.png").write_bytes(b"OLD")
    painter = FakePainter()
    drawn = Illustrator(painter, tmp_path, "photo").redraw(7, 2, old, "a fresh scene", "comic")

    assert painter.prompts == [f"{STYLES['comic']} {NO_TEXT} a fresh scene"]
    assert drawn.scene == "a fresh scene"
    assert drawn.image.startswith("7-2-") and drawn.image.endswith(".png")
    assert (tmp_path / drawn.image).read_bytes() == b"PNG0"
    assert not (tmp_path / "old.png").exists()

    with pytest.raises(GenerationError):
        Illustrator(FakePainter(blank={0}), tmp_path).redraw(7, 2, drawn, "another", "")


class FakeCli:
    def __init__(self, scene: str):
        self.scene = scene
        self.prompt = ""

    def run(self, prompt: str, schema: dict, on_event=None) -> dict:
        self.prompt = prompt
        return {"structured_output": {"scene": self.scene}}


def test_scene_writer_names_the_word_and_the_scene_to_avoid():
    item = sample_content().vocabulary[0].model_copy(update={"scene": "the old scene"})
    cli = FakeCli("  a new scene ")
    assert SceneWriter(cli).write(item) == "a new scene"
    assert "Word: word0 (noun)" in cli.prompt and "the old scene" in cli.prompt
    with pytest.raises(GenerationError):
        SceneWriter(FakeCli("")).write(item)
