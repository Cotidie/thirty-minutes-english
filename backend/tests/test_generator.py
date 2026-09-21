import json

import pytest

from app.exclusions import Exclusions
from app.generator import ClaudeCliGenerator, GenerationError
from tests.conftest import sample_content


def test_parse_result_returns_content():
    payload = sample_content().model_dump()
    parsed = ClaudeCliGenerator.parse_result({"is_error": False, "structured_output": payload})
    assert parsed.article.title == "Twins at Work"
    assert len(parsed.vocabulary) == 10


def test_parse_result_raises_on_error_envelope():
    with pytest.raises(GenerationError, match="rate limited"):
        ClaudeCliGenerator.parse_result({"is_error": True, "result": "rate limited"})


def test_parse_result_raises_on_missing_structured_output():
    with pytest.raises(GenerationError):
        ClaudeCliGenerator.parse_result({"is_error": False, "result": "plain text"})


def test_build_command_includes_model_effort_and_schema():
    gen = ClaudeCliGenerator(model="sonnet", effort="high")
    cmd = gen.build_command()
    assert cmd[0] == "claude"
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert set(schema["required"]) == {"topic", "expressions", "article", "vocabulary"}
    assert schema["properties"]["expressions"]["minItems"] == 5
    assert schema["properties"]["vocabulary"]["maxItems"] == 10


def test_default_effort_is_xhigh():
    cmd = ClaudeCliGenerator(model="sonnet").build_command()
    assert cmd[cmd.index("--effort") + 1] == "xhigh"


def test_prompt_states_counts_and_relaxed_vocabulary_rule():
    prompt = ClaudeCliGenerator(model="sonnet").build_prompt("x")
    assert "5 general-purpose expressions" in prompt
    assert "10 words at B2 to C1+" in prompt
    assert "even if they do not appear in the article" in prompt


def test_build_command_exposes_skill_read_builtin_web_and_firecrawl():
    cmd = ClaudeCliGenerator(model="sonnet").build_command()
    assert cmd[cmd.index("--tools") + 1] == "Skill,Read,WebSearch,WebFetch"
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    assert allowed == [
        "Skill", "Read", "WebSearch", "WebFetch",
        "mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_scrape",
    ]
    assert cmd[cmd.index("--setting-sources") + 1] == "user"
    assert "--restricted" not in cmd
    assert "--strict-mcp-config" in cmd
    mcp = json.loads(cmd[cmd.index("--mcp-config") + 1])
    assert list(mcp["mcpServers"]) == ["firecrawl"]


def test_prompt_mentions_topic():
    gen = ClaudeCliGenerator(model="sonnet")
    assert "Digital twins" in gen.build_prompt("Digital twins")


def test_prompt_falls_back_to_builtin_web_search():
    prompt = ClaudeCliGenerator(model="sonnet").build_prompt("x")
    assert "firecrawl_search when it is offered and WebSearch when it is missing or fails" in prompt


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


def test_schema_and_prompt_ask_for_sources():
    gen = ClaudeCliGenerator(model="sonnet")
    schema = json.loads(gen.build_command()[gen.build_command().index("--json-schema") + 1])
    assert "sources" in schema["properties"]["article"]["required"]
    assert "list only the web pages you actually drew on" in gen.build_prompt("x")


def test_prompt_lists_exclusions_only_when_given():
    gen = ClaudeCliGenerator(model="sonnet")
    assert "HARD CONSTRAINT" not in gen.build_prompt("x")
    assert "HARD CONSTRAINT" not in gen.build_prompt("x", Exclusions())
    prompt = gen.build_prompt("x", Exclusions(("on the fence", "push back"), ("scrutiny",)))
    assert "Banned expressions: on the fence; push back" in prompt
    assert "Banned words: scrutiny" in prompt
