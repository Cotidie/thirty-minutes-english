import pytest
from claude_agent_sdk import CLINotFoundError

from app.llm import Claude, GenerationError
from tests.fake_claude import FakeQuery, assistant, result, text, tool_use


def test_run_returns_the_structured_output_and_passes_every_message_on():
    fake = FakeQuery(assistant(tool_use("WebSearch")), assistant(text()), result({"x": 1}))
    seen = []
    assert Claude("sonnet", query=fake).run("hi", {"type": "object"}, seen.append) == {"x": 1}
    assert len(seen) == 3
    assert fake.calls[0][0] == "hi"


def test_an_error_result_raises_with_its_text():
    with pytest.raises(GenerationError, match="rate limited"):
        Claude("sonnet", query=FakeQuery(result(is_error=True, text="rate limited"))).run("p", {})


def test_a_result_without_structured_output_raises():
    with pytest.raises(GenerationError, match="no structured output"):
        Claude("sonnet", query=FakeQuery(result(None))).run("p", {})


def test_no_result_at_all_raises():
    with pytest.raises(GenerationError, match="no result"):
        Claude("sonnet", query=FakeQuery(assistant(text()))).run("p", {})


def test_sdk_errors_and_timeouts_become_generation_errors():
    with pytest.raises(GenerationError, match="claude failed"):
        Claude("sonnet", query=FakeQuery(error=CLINotFoundError("no cli"))).run("p", {})
    with pytest.raises(GenerationError, match="timed out"):
        Claude("sonnet", timeout_s=0.05, query=FakeQuery(hang=True)).run("p", {})
