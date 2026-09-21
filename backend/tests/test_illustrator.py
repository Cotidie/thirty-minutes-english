import base64
import threading

from app.illustrator import STYLE, Illustrator, OpenRouterPainter
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

    assert painter.prompts[0] == f"{STYLE} scene 0"
    assert [v.image for v in done.vocabulary] == [f"job1-{i}.png" for i in range(len(content.vocabulary))]
    assert (tmp_path / "images" / "job1-2.png").read_bytes() == b"PNG2"
    assert content.vocabulary[0].image is None  # the input is untouched


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
