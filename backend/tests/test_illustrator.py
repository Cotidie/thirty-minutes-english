from app.illustrator import STYLE, Illustrator
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
