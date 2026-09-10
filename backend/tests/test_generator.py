import json

import pytest

from app.generator import ClaudeCliGenerator, GenerationError
from tests.conftest import sample_content


def test_parse_cli_output_returns_content():
    payload = sample_content().model_dump()
    stdout = json.dumps({"is_error": False, "structured_output": payload})
    parsed = ClaudeCliGenerator.parse_output(stdout)
    assert parsed.article.title == "Twins at Work"
    assert len(parsed.vocabulary) == 12


def test_parse_cli_output_raises_on_error_envelope():
    stdout = json.dumps({"is_error": True, "result": "rate limited"})
    with pytest.raises(GenerationError, match="rate limited"):
        ClaudeCliGenerator.parse_output(stdout)


def test_parse_cli_output_raises_on_missing_structured_output():
    stdout = json.dumps({"is_error": False, "result": "plain text"})
    with pytest.raises(GenerationError):
        ClaudeCliGenerator.parse_output(stdout)


def test_build_command_includes_model_effort_and_schema():
    gen = ClaudeCliGenerator(model="sonnet", effort="high")
    cmd = gen.build_command()
    assert cmd[0] == "claude"
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--effort") + 1] == "high"
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert set(schema["required"]) == {"topic", "expressions", "article", "vocabulary"}
    assert schema["properties"]["expressions"]["minItems"] == 6
    assert schema["properties"]["vocabulary"]["maxItems"] == 12


def test_default_effort_is_xhigh():
    cmd = ClaudeCliGenerator(model="sonnet").build_command()
    assert cmd[cmd.index("--effort") + 1] == "xhigh"


def test_prompt_states_counts_and_relaxed_vocabulary_rule():
    prompt = ClaudeCliGenerator(model="sonnet").build_prompt("x")
    assert "6 general-purpose expressions" in prompt
    assert "12 words at B2 to C1+" in prompt
    assert "even if they do not appear in the article" in prompt


def test_build_command_exposes_skill_read_and_firecrawl_only():
    cmd = ClaudeCliGenerator(model="sonnet").build_command()
    assert cmd[cmd.index("--tools") + 1] == "Skill,Read"
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    assert allowed == ["Skill", "Read", "mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_scrape"]
    assert cmd[cmd.index("--setting-sources") + 1] == "user"
    assert "--restricted" not in cmd
    assert "--strict-mcp-config" in cmd
    mcp = json.loads(cmd[cmd.index("--mcp-config") + 1])
    assert list(mcp["mcpServers"]) == ["firecrawl"]


def test_prompt_mentions_topic():
    gen = ClaudeCliGenerator(model="sonnet")
    assert "Digital twins" in gen.build_prompt("Digital twins")


def test_prompt_lists_skills_when_configured():
    gen = ClaudeCliGenerator(model="sonnet", skills=("stop-slop", "cotidie:write-like-me"))
    prompt = gen.build_prompt("Digital twins")
    assert prompt.startswith("Before writing, invoke each of these skills")
    assert "stop-slop, cotidie:write-like-me" in prompt
    assert "Digital twins" in prompt


def test_prompt_has_no_skill_preamble_by_default():
    assert not ClaudeCliGenerator(model="sonnet").build_prompt("x").startswith("Before writing")


def test_prompt_asks_for_short_discussion_questions():
    prompt = ClaudeCliGenerator(model="sonnet").build_prompt("x")
    assert "at most 14 words" in prompt
