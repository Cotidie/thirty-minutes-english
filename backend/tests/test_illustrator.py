import base64
from contextlib import asynccontextmanager

import pytest
from mcp.types import CallToolResult, ImageContent, TextContent

from app.db import Database
from app.llm import GenerationError
from app.mcp_client import McpError
from app.pictures.files import PictureFiles
from app.pictures.illustrator import IMAGE_RULES, STYLES, Illustrator
from app.pictures.painters import Drawn, OpenRouterPainter, painter_for
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


def test_painter_for_needs_the_key():
    assert isinstance(painter_for("sk-or", ""), OpenRouterPainter)
    assert painter_for("", "") is None


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


def test_a_batch_is_foreseen_to_take_as_long_as_one_picture():
    assert OpenRouterPainter(FakeServer({}), "m", Stats(20)).expected_seconds(10) == 20  # side by side
    assert OpenRouterPainter(FakeServer({}), "m").expected_seconds(10) is None  # nothing drawn yet
