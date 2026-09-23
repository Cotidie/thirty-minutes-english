import asyncio
import base64
import json
from contextlib import asynccontextmanager

import httpx2
import pytest
from mcp.types import CallToolResult, ImageContent, TextContent

from app.llm import GenerationError
from app.mcp_client import McpError
from app.pictures.illustrator import IMAGE_RULES, STYLES, Illustrator
from app.pictures.painters import (
    ComfyPainter,
    OpenRouterPainter,
    fetch_url,
    finished,
    painter_for,
)
from app.pictures.scenes import SceneWriter, Spark
from tests.conftest import sample_content


class FakePainter:
    def __init__(self, blank: set[int] = frozenset()):
        self.blank = blank
        self.prompts: list[str] = []

    def paint(self, prompts: list[str], on_drawn=None) -> list[bytes | None]:
        self.prompts = prompts
        for i in range(len(prompts)):
            if on_drawn:
                on_drawn(i + 1)
        return [None if i in self.blank else f"PNG{i}".encode() for i in range(len(prompts))]


def test_every_word_with_a_scene_gets_its_picture_file(tmp_path):
    content = sample_content()
    painter = FakePainter()
    done = Illustrator(painter, tmp_path / "images").illustrate("job1", content)

    assert painter.prompts[0] == f"{STYLES['photo']} {IMAGE_RULES} scene 0"
    assert [v.image for v in done.vocabulary] == [f"job1-{i}.png" for i in range(len(content.vocabulary))]
    assert (tmp_path / "images" / "job1-2.png").read_bytes() == b"PNG2"
    assert content.vocabulary[0].image is None  # the input is untouched


def test_the_chosen_style_leads_the_prompt_and_an_unknown_one_falls_back_to_photo(tmp_path):
    assert Illustrator(FakePainter(), tmp_path, "comic").prompt("a dog") == f"{STYLES['comic']} {IMAGE_RULES} a dog"
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


class FakeServer:
    """Stands in for McpHttp: one session whose calls answer per tool (a list, in order) or per prompt (a dict)."""

    def __init__(self, answers: dict):
        self.answers = {tool: list(a) if isinstance(a, list) else a for tool, a in answers.items()}
        self.calls: list[tuple[str, dict]] = []

    @asynccontextmanager
    async def session(self):
        yield self

    async def call(self, tool: str, arguments: dict) -> CallToolResult:
        self.calls.append((tool, arguments))
        answers = self.answers[tool]
        answer = answers.pop(0) if isinstance(answers, list) else answers[arguments["prompt"]]
        if isinstance(answer, Exception):
            raise answer
        return answer


class RefusedServer:
    @asynccontextmanager
    async def session(self):
        raise McpError("https://mcp: HTTP 401")
        yield


def text(data) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(data))])


def test_openrouter_draws_every_prompt_on_one_session_and_shrugs_off_a_failed_one():
    png = base64.b64encode(b"PNG-a").decode()
    server = FakeServer({"generate-image": {
        "a": CallToolResult(content=[TextContent(type="text", text="here"), ImageContent(type="image", data=png, mime_type="image/png")]),
        "b": McpError("generate-image: over budget"),
        "c": CallToolResult(content=[TextContent(type="text", text="nothing")]),
    }})
    pictures = OpenRouterPainter(server, "google/gemini-3-pro-image").paint(["a", "b", "c"])

    assert pictures == [b"PNG-a", None, None]
    assert [c[1] for c in server.calls] == [{"prompt": p, "model": "google/gemini-3-pro-image"} for p in "abc"]


def test_a_refused_key_leaves_every_picture_blank():
    assert OpenRouterPainter(RefusedServer(), "m").paint(["a", "b"]) == [None, None]
    assert ComfyPainter(RefusedServer(), "m").paint(["a"]) == [None]


def test_comfy_submits_one_batch_waits_and_fetches_each_job_in_order():
    server = FakeServer({
        "submit_batch": [text({"batch_id": "b1", "job_ids": ["j0", "j1", "j2"]})],
        "wait_for_batch": [
            text({"timed_out": True, "summary": {"pending": 2, "ready": 1, "failed": 0}}),
            text({"timed_out": False, "summary": {"pending": 0, "ready": 2, "failed": 1}}),
        ],
        "get_batch_output": [text({"outputs": [{"job_id": "j2", "url": "https://x/2"}, {"job_id": "j0", "url": "https://x/0"}]})],
    })
    fetched = []
    counts: list[int] = []

    async def fetch(url):
        fetched.append(url)
        if url.endswith("/2"):
            raise httpx2.ConnectError("gone")
        return b"PNG" + url[-1].encode()

    pictures = ComfyPainter(server, "vertexai/nano-banana-pro", fetch=fetch).paint(["a", "b", "c"], counts.append)

    assert pictures == [b"PNG0", None, None]
    assert counts == [1, 3]  # each wait round reports the batch's finished pictures
    submit = server.calls[0][1]
    assert submit["confirm"] is True
    assert [i["prompt"] for i in submit["items"]] == ["a", "b", "c"]
    assert submit["items"][0]["model"] == "vertexai/nano-banana-pro"
    assert [c[0] for c in server.calls] == ["submit_batch", "wait_for_batch", "wait_for_batch", "get_batch_output"]
    assert sorted(fetched) == ["https://x/0", "https://x/2"]


def test_comfy_spells_an_openai_model_as_the_partner_slug_plus_variant_and_survives_a_refused_batch():
    server = FakeServer({"submit_batch": [McpError("submit_batch: no credits")]})
    assert ComfyPainter(server, "openai/gpt-image-2.5-flare").paint(["a", "b"]) == [None, None]
    item = server.calls[0][1]["items"][0]
    assert item["model"] == "openai/images-generations"
    assert item["params"] == {"model": "gpt-image-2.5-flare"}


def test_painter_for_picks_the_provider_and_needs_its_key():
    keys = {"openrouter": "sk-or", "comfy": ""}
    assert isinstance(painter_for("openrouter", "", keys), OpenRouterPainter)
    assert painter_for("comfy", "", keys) is None
    assert isinstance(painter_for("comfy", "", {"comfy": "comfyui-1"}), ComfyPainter)
    assert painter_for("off", "", keys) is None


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


def test_redraw_draws_the_new_scene_in_the_asked_style_under_a_new_name_and_discard_drops_a_file(tmp_path):
    content = sample_content()
    old = content.vocabulary[2].model_copy(update={"image": "old.png"})
    (tmp_path / "old.png").write_bytes(b"OLD")
    painter = FakePainter()
    drawn = Illustrator(painter, tmp_path, "photo").redraw(7, 2, old, "a fresh scene", "comic")

    assert painter.prompts == [f"{STYLES['comic']} {IMAGE_RULES} a fresh scene"]
    assert drawn.scene == "a fresh scene"
    assert drawn.image.startswith("7-2-") and drawn.image.endswith(".png")
    assert (tmp_path / drawn.image).read_bytes() == b"PNG0"
    assert (tmp_path / "old.png").exists()  # dropped only once the new name is stored
    Illustrator(painter, tmp_path).discard("old.png")
    Illustrator(painter, tmp_path).discard(None)
    assert not (tmp_path / "old.png").exists()

    with pytest.raises(GenerationError):
        Illustrator(FakePainter(blank={0}), tmp_path).redraw(7, 2, drawn, "another", "")


class FakeCli:
    def __init__(self, scene: str):
        self.scene = scene
        self.prompt = ""

    def run(self, prompt: str, schema: dict, on_message=None) -> dict:
        self.prompt = prompt
        return {"scene": self.scene}


def test_scene_writer_names_the_word_the_scene_to_avoid_and_a_rolled_spark():
    import random

    item = sample_content().vocabulary[0].model_copy(update={"scene": "the old scene"})
    cli = FakeCli("  a new scene ")
    assert SceneWriter(cli, random.Random(3)).write(item) == "a new scene"
    assert "Word: word0 (noun)" in cli.prompt and "the old scene" in cli.prompt
    spark = Spark.roll(random.Random(3))
    assert str(spark) in cli.prompt and spark.place in str(spark)
    assert Spark.roll(random.Random(1)) != Spark.roll(random.Random(2))
    with pytest.raises(GenerationError):
        SceneWriter(FakeCli("")).write(item)


def test_the_illustrator_reports_each_finished_picture(tmp_path):
    counts: list[int] = []
    content = sample_content()
    Illustrator(FakePainter(), tmp_path / "images").illustrate("job1", content, counts.append)
    assert counts == list(range(1, len(content.vocabulary) + 1))


def test_a_batch_without_a_summary_is_counted_from_its_jobs():
    assert finished({"jobs": [{"state": "ready"}, {"state": "pending"}, {"state": "failed"}]}) == 2
    assert finished({"timed_out": True}) == 0


async def fetch_ok(url):
    return b"PNG" + url[-1].encode()


def comfy_server(waits: list, outputs: list[str]) -> FakeServer:
    return FakeServer({
        "submit_batch": [text({"batch_id": "b1", "job_ids": ["j0", "j1"]})],
        "wait_for_batch": waits,
        "get_batch_output": [text({"outputs": [{"job_id": j, "url": f"https://x/{j[-1]}"} for j in outputs]})],
        "cancel_job": [text("cancelled"), McpError("cancel_job: already finished")],
    })


def test_comfy_reconnects_when_the_connection_drops_and_waits_on():
    server = comfy_server(
        [McpError("dropped"), text({"timed_out": False, "summary": {"ready": 2}})], ["j0", "j1"]
    )
    assert ComfyPainter(server, "m", fetch=fetch_ok).paint(["a", "b"]) == [b"PNG0", b"PNG1"]
    assert [c[0] for c in server.calls] == ["submit_batch", "wait_for_batch", "wait_for_batch", "get_batch_output"]


def test_comfy_keeps_the_pictures_already_drawn_when_it_gives_up():
    server = comfy_server([McpError("dropped")] * 3, ["j0"])
    assert ComfyPainter(server, "m", fetch=fetch_ok).paint(["a", "b"]) == [b"PNG0", None]


def test_a_cancel_during_the_wait_cancels_every_comfy_job():
    server = comfy_server([text({"timed_out": True, "summary": {"ready": 0}})], [])

    def cancel(_):
        raise KeyError("cancelled")

    with pytest.raises(KeyError):
        ComfyPainter(server, "m", fetch=fetch_ok).paint(["a", "b"], cancel)
    assert [c[1] for c in server.calls if c[0] == "cancel_job"] == [{"prompt_id": "j0"}, {"prompt_id": "j1"}]


def test_openrouter_reports_what_each_picture_cost():
    png = base64.b64encode(b"PNG").decode()
    billed = CallToolResult(content=[ImageContent(type="image", data=png, mime_type="image/png"), TextContent(type="text", text="(model: m, cost: $0.134, total tokens: 1120)")])
    unbilled = CallToolResult(content=[ImageContent(type="image", data=png, mime_type="image/png")])
    server = FakeServer({"generate-image": {"a": billed, "b": unbilled}})
    costs: list[tuple[str, float]] = []
    OpenRouterPainter(server, "google/gemini-3-pro-image", lambda model, cost: costs.append((model, cost))).paint(["a", "b"])
    assert costs == [("google/gemini-3-pro-image", 0.134)]
