import json

import pytest

from app.generator import ClaudeCliGenerator, GenerationError
from tests.conftest import sample_content


def test_parse_cli_output_returns_content():
    payload = sample_content().model_dump()
    stdout = json.dumps({"is_error": False, "structured_output": payload})
    parsed = ClaudeCliGenerator.parse_output(stdout)
    assert parsed.article.title == "Twins at Work"
    assert len(parsed.vocabulary) == 8


def test_parse_cli_output_raises_on_error_envelope():
    stdout = json.dumps({"is_error": True, "result": "rate limited"})
    with pytest.raises(GenerationError, match="rate limited"):
        ClaudeCliGenerator.parse_output(stdout)


def test_parse_cli_output_raises_on_missing_structured_output():
    stdout = json.dumps({"is_error": False, "result": "plain text"})
    with pytest.raises(GenerationError):
        ClaudeCliGenerator.parse_output(stdout)


def test_build_command_includes_model_and_schema():
    gen = ClaudeCliGenerator(model="sonnet")
    cmd = gen.build_command()
    assert cmd[0] == "claude"
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "sonnet"
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert set(schema["required"]) == {"topic", "expressions", "article", "vocabulary"}


def test_prompt_mentions_topic():
    gen = ClaudeCliGenerator(model="sonnet")
    assert "Digital twins" in gen.build_prompt("Digital twins")
