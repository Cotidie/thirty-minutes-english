from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.claude_cli import GenerationError
from app.coaching.phrasing import PhrasingMarker, breaks_in
from app.db import Database
from app.main import create_app
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor

PARAGRAPH = "The usual story is simple. The Soviet Union launched Sputnik in 1957."


class FakeCli:
    def __init__(self, marked: str):
        self.marked = marked
        self.prompts: list[str] = []

    def run(self, prompt: str, schema: dict, on_event=None) -> dict:
        self.prompts.append(prompt)
        assert schema["required"] == ["marked"]
        return {"structured_output": {"marked": self.marked}}


@pytest.fixture
def agent_dir(tmp_path) -> Path:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "phrasing.md").write_text("Mark this:\n{{paragraph}}")
    return tmp_path


def test_breaks_are_the_indices_of_the_words_after_each_slash():
    assert breaks_in("The usual story / is simple. The Soviet Union / launched Sputnik / in 1957.", PARAGRAPH) == [3, 8, 10]


def test_breaks_tolerate_slash_spacing_and_stray_edges():
    assert breaks_in(" / The usual story/is simple. The Soviet Union launched Sputnik in 1957. / ", PARAGRAPH) == [3]


def test_breaks_reject_an_answer_that_changed_the_words():
    with pytest.raises(GenerationError):
        breaks_in("The usual story / is easy. The Soviet Union launched Sputnik in 1957.", PARAGRAPH)


def test_marker_fills_the_prompt_and_returns_breaks(agent_dir):
    cli = FakeCli("The usual story / is simple. The Soviet Union launched Sputnik in 1957.")
    assert PhrasingMarker(cli, agent_dir).mark(PARAGRAPH) == [3]
    assert cli.prompts == [f"Mark this:\n{PARAGRAPH}"]


class FakeMarker:
    def __init__(self, breaks: list[int] | Exception):
        self.breaks = breaks
        self.calls = 0

    def mark(self, paragraph: str) -> list[int]:
        self.calls += 1
        if isinstance(self.breaks, Exception):
            raise self.breaks
        return self.breaks


def client_with(tmp_path, marker) -> TestClient:
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator(), phrasing=marker), InlineExecutor())
    return TestClient(app)


def test_phrasing_endpoint_marks_once_and_serves_the_cache_after(tmp_path):
    marker = FakeMarker([3, 9])
    with client_with(tmp_path, marker) as c:
        first = c.post("/api/phrasing", json={"paragraph": PARAGRAPH})
        second = c.post("/api/phrasing", json={"paragraph": PARAGRAPH})
    assert first.status_code == 200
    assert first.json() == {"breaks": [3, 9]}
    assert second.json() == {"breaks": [3, 9]}
    assert marker.calls == 1


def test_phrasing_endpoint_reports_a_failed_run(tmp_path):
    with client_with(tmp_path, FakeMarker(GenerationError("claude timed out after 90s"))) as c:
        res = c.post("/api/phrasing", json={"paragraph": PARAGRAPH})
    assert res.status_code == 502
    assert "claude timed out" in res.json()["detail"]


def test_phrasing_endpoint_is_off_without_a_marker(tmp_path):
    with client_with(tmp_path, None) as c:
        res = c.post("/api/phrasing", json={"paragraph": PARAGRAPH})
    assert res.status_code == 503
