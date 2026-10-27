import asyncio
import base64
import json
from contextlib import asynccontextmanager

import httpx2
import pytest
from mcp.types import CallToolResult, ImageContent, TextContent

from app.db import Database
from app.llm import GenerationError
from app.mcp_client import McpError
from app.pictures.files import PictureFiles
from app.pictures.illustrator import IMAGE_RULES, STYLES, Illustrator
from app.pictures.painters import (
    ComfyPainter,
    Drawn,
    OpenRouterPainter,
    fetch_url,
    finished,
    painter_for,
)
from app.pictures.scenes import Scene, SceneWriter, Spark
from tests.conftest import sample_draft


class FakePainter:
    def __init__(self, blank: set[int] = frozenset()):
        self.blank = blank
        self.prompts: list[str] = []

    def paint(self, prompts: list[str], on_drawn=None, on_picture=None) -> list[Drawn | None]:
        self.prompts = prompts
        pictures = [None if i in self.blank else Drawn(f"PNG{i}".encode(), "fake", 2.0) for i in range(len(prompts))]
        for i, drawn in enumerate(pictures):
            if drawn and on_picture:
                on_picture(i, drawn)
            if on_drawn:
                on_drawn(i + 1)
        return pictures

    def expected_seconds(self, count: int) -> float | None:
        return None


def illustrator_for(tmp_path, painter=None, style: str = "photo") -> tuple[Illustrator, Database, PictureFiles]:
    db = Database(tmp_path / "s.db")
    files = PictureFiles(tmp_path / "images")
    return Illustrator(painter or FakePainter(), db.pictures, files, style), db, files


def landing(into: list):
    return lambda index, field, picture_id: into.append((index, field, picture_id))


def test_every_word_gets_its_example_and_its_scene_drawn(tmp_path):
    words = sample_draft().vocabulary
    painter = FakePainter()
    illustrator, _, files = illustrator_for(tmp_path, painter)
    landed = []
    illustrator.illustrate("job1", words, None, landing(landed))

    assert 'This sentence as one moment: "ex 0" In it, "word0" (noun) means: def 0.' in painter.prompts[0]
    assert painter.prompts[1] == f"{STYLES['photo']} {IMAGE_RULES} scene 0"
    assert [(i, f) for i, f, _ in landed] == [(i, f) for i in range(len(words)) for f in ("example_image", "image")]
    picture = {(i, f): pid for i, f, pid in landed}
    assert files.path(picture[2, "example_image"]).read_bytes() == b"PNG4"
    assert files.path(picture[2, "image"]).read_bytes() == b"PNG5"


def test_each_drawn_picture_is_one_row_and_one_file_named_by_the_row(tmp_path):
    illustrator, db, files = illustrator_for(tmp_path)
    landed = []
    illustrator.illustrate("j", sample_draft().vocabulary, None, landing(landed))
    ids = [pid for _, _, pid in landed]
    assert len(set(ids)) == len(ids)
    assert sorted((tmp_path / "images").iterdir()) == sorted(files.path(pid) for pid in ids)
    assert files.path(ids[0]).name == f"{ids[0]}.png"
    assert db.pictures.stats()["fake"].seconds == 2.0


def test_a_picture_whose_word_went_away_loses_its_file(tmp_path):
    illustrator, _, files = illustrator_for(tmp_path)
    landed = []

    def land(index, field, picture_id):
        if index == 1:
            raise KeyError(index)  # the word's session was deleted while drawing
        landed.append(picture_id)

    illustrator.illustrate("j", sample_draft().vocabulary[:2], None, land)
    assert len(landed) == 2
    assert sorted(f.name for f in (tmp_path / "images").iterdir()) == sorted(files.name(pid) for pid in landed)


def test_the_article_scene_is_drawn_with_the_words_and_handed_over_on_its_own(tmp_path):
    painter = FakePainter()
    illustrator, _, files = illustrator_for(tmp_path, painter)
    words = sample_draft().vocabulary[:1]
    landed, article = [], []
    assert illustrator.count(words, "a tram stop") == 3 and illustrator.count(words) == 2
    illustrator.illustrate("j", words, None, landing(landed), "a tram stop", article.append)
    assert painter.prompts[-1] == f"{STYLES['photo']} {IMAGE_RULES} a tram stop"
    assert len(landed) == 2 and len(article) == 1 and files.path(article[0]).is_file()


def test_the_chosen_style_leads_the_prompt_and_an_unknown_one_falls_back_to_photo(tmp_path):
    assert illustrator_for(tmp_path, style="comic")[0].prompt("a dog") == f"{STYLES['comic']} {IMAGE_RULES} a dog"
    assert illustrator_for(tmp_path, style="nope")[0].prompt("a dog").startswith(STYLES["photo"])


def test_a_word_without_a_scene_gets_only_its_example_and_a_failed_picture_stays_bare(tmp_path):
    words = list(sample_draft().vocabulary)
    words[1] = words[1].model_copy(update={"scene": None})
    illustrator, db, _ = illustrator_for(tmp_path, FakePainter(blank={3}))  # prompts: ex0, scene0, ex1, ex2, scene2
    landed = []
    illustrator.illustrate("j", words, None, landing(landed))

    assert illustrator.count(words) == 2 * len(words) - 1
    assert [f for i, f, _ in landed if i == 1] == ["example_image"]
    assert [f for i, f, _ in landed if i == 2] == ["image"]
    assert len(list((tmp_path / "images").iterdir())) == len(landed) == 2 * len(words) - 2
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pictures").fetchone()[0] == len(landed)  # a failed picture leaves no row


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

    assert [p and p.png for p in pictures] == [b"PNG-a", None, None]
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

    assert [p and p.png for p in pictures] == [b"PNG0", None, None]
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


def test_redraw_draws_the_new_scene_in_the_configured_style_as_a_new_picture_and_remove_drops_a_file(tmp_path):
    painter = FakePainter()
    illustrator, _, files = illustrator_for(tmp_path, painter, style="comic")
    picture = illustrator.redraw(Scene("a fresh scene", "why it fits"))

    assert painter.prompts == [f"{STYLES['comic']} {IMAGE_RULES} a fresh scene"]
    assert files.path(picture).read_bytes() == b"PNG0"

    again = illustrator.redraw_example(sample_draft().vocabulary[2])
    assert painter.prompts[0].startswith(STYLES["comic"]) and '"ex 2"' in painter.prompts[0]
    assert again == picture + 1 and files.path(again).is_file()

    files.remove(picture)  # the caller drops the old file once the new id is stored
    files.remove(None)
    assert not files.path(picture).exists() and files.path(again).exists()

    with pytest.raises(GenerationError):
        illustrator_for(tmp_path, FakePainter(blank={0}))[0].redraw(Scene("another", ""))


class FakeCli:
    def __init__(self, scene: str, caption: str = "why"):
        self.scene = scene
        self.caption = caption
        self.prompt = ""

    def run(self, prompt: str, schema: dict, on_message=None) -> dict:
        self.prompt = prompt
        return {"scene": self.scene, "caption": self.caption}


def test_scene_writer_names_the_word_the_scene_to_avoid_and_a_rolled_spark():
    import random

    item = sample_draft().vocabulary[0].model_copy(update={"scene": "the old scene"})
    cli = FakeCli("  a new scene ", " the caption ")
    assert SceneWriter(cli, random.Random(3)).write(item) == Scene("a new scene", "the caption")
    assert "caption" in cli.prompt
    assert "Word: word0 (noun)" in cli.prompt and "the old scene" in cli.prompt
    spark = Spark.roll(random.Random(3))
    assert str(spark) in cli.prompt and spark.place in str(spark)
    assert Spark.roll(random.Random(1)) != Spark.roll(random.Random(2))
    with pytest.raises(GenerationError):
        SceneWriter(FakeCli("")).write(item)


def test_the_illustrator_reports_each_finished_picture(tmp_path):
    counts: list[int] = []
    kept: list[tuple] = []
    words = sample_draft().vocabulary
    illustrator, _, files = illustrator_for(tmp_path)
    illustrator.illustrate("job1", words, counts.append, landing(kept))
    assert counts == list(range(1, 2 * len(words) + 1))
    assert [(i, f) for i, f, _ in kept[:3]] == [(0, "example_image"), (0, "image"), (1, "example_image")]
    assert files.path(kept[0][2]).exists()


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
    assert [p and p.png for p in ComfyPainter(server, "m", fetch=fetch_ok).paint(["a", "b"])] == [b"PNG0", b"PNG1"]
    assert [c[0] for c in server.calls] == ["submit_batch", "wait_for_batch", "wait_for_batch", "get_batch_output"]


def test_comfy_keeps_the_pictures_already_drawn_when_it_gives_up():
    server = comfy_server([McpError("dropped")] * 3, ["j0"])
    assert [p and p.png for p in ComfyPainter(server, "m", fetch=fetch_ok).paint(["a", "b"])] == [b"PNG0", None]


def test_a_cancel_during_the_wait_cancels_every_comfy_job():
    server = comfy_server([text({"timed_out": True, "summary": {"ready": 0}})], [])

    def cancel(_):
        raise KeyError("cancelled")

    with pytest.raises(KeyError):
        ComfyPainter(server, "m", fetch=fetch_ok).paint(["a", "b"], cancel)
    assert [c[1] for c in server.calls if c[0] == "cancel_job"] == [{"prompt_id": "j0"}, {"prompt_id": "j1"}]


class Stats:
    """Knows `known` seconds per picture for every model."""

    def __init__(self, known: float | None = None) -> None:
        self.known = known

    def seconds(self, model):
        return self.known


def test_openrouter_times_each_picture_and_keeps_what_it_cost():
    png = base64.b64encode(b"PNG").decode()
    billed = CallToolResult(content=[ImageContent(type="image", data=png, mime_type="image/png"), TextContent(type="text", text="(model: m, cost: $0.134, total tokens: 1120)")])
    unbilled = CallToolResult(content=[ImageContent(type="image", data=png, mime_type="image/png")])
    blank = CallToolResult(content=[TextContent(type="text", text="refused, cost: $0.002")])
    server = FakeServer({"generate-image": {"a": billed, "b": unbilled, "c": blank}})
    drawn = OpenRouterPainter(server, "m").paint(["a", "b", "c"])
    assert [d and (d.model, d.seconds >= 0, d.cost) for d in drawn] == [("m", True, 0.134), ("m", True, None), None]


def test_comfy_shares_the_batch_time_over_the_pictures_that_came_back():
    server = comfy_server([text({"timed_out": False, "summary": {"ready": 1, "failed": 1}})], ["j0"])
    [first, second] = ComfyPainter(server, "m", fetch=fetch_ok).paint(["a", "b"])
    assert (first.png, first.model, first.cost, second) == (b"PNG0", "m", None, None)
    assert first.seconds >= 0


def test_the_wait_foreseen_for_a_batch_follows_how_each_provider_draws():
    assert OpenRouterPainter(FakeServer({}), "m", Stats(20)).expected_seconds(10) == 20  # side by side
    assert ComfyPainter(FakeServer({}), "m", Stats(20)).expected_seconds(10) == 200  # one after another
    assert ComfyPainter(FakeServer({}), "m").expected_seconds(10) is None  # nothing drawn yet
