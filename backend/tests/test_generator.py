import jsonschema
import pytest

from app.generation.exclusions import Exclusions
from app.generation.generator import (
    APP_SKILL,
    CHECK_ITEMS_RULE,
    PLUGIN_DIR,
    SESSION_SCHEMA,
    ClaudeGenerator,
    check_items_reply,
)
from app.generation.progress import Progress, Stage
from app.llm import GenerationError
from tests.conftest import sample_content
from tests.fake_claude import FakeQuery, assistant, result, tool_use


def generator_with(fake: FakeQuery, **kwargs) -> ClaudeGenerator:
    gen = ClaudeGenerator(model="sonnet", **kwargs)
    object.__setattr__(gen.claude, "query", fake)
    return gen


def test_generate_validates_the_payload_and_reports_progress():
    fake = FakeQuery(assistant(tool_use("WebSearch")), assistant(tool_use("StructuredOutput")), result(sample_content().model_dump()))
    seen = []
    content = generator_with(fake).generate("Digital twins", seen.append)
    assert content.article.title == "Twins at Work"
    assert seen == [Progress(Stage.SEARCHING, 1), Progress(Stage.FINALIZING, 1)]


def test_a_payload_that_fails_validation_raises():
    with pytest.raises(GenerationError, match="validation"):
        generator_with(FakeQuery(result({"topic": "x"}))).generate("x")


def test_past_items_go_to_a_check_tool_not_the_prompt():
    fake = FakeQuery(result(sample_content().model_dump()))
    generator_with(fake).generate("x", exclude=Exclusions(("push back",), ("scrutiny",)))
    prompt, options = fake.calls[0]
    assert CHECK_ITEMS_RULE in prompt and "push back" not in prompt
    assert "session" in options.mcp_servers
    assert "mcp__session__check_items" in options.allowed_tools


def test_no_check_tool_without_past_items():
    fake = FakeQuery(result(sample_content().model_dump()))
    generator_with(fake).generate("x", exclude=Exclusions())
    prompt, options = fake.calls[0]
    assert CHECK_ITEMS_RULE not in prompt and "session" not in options.mcp_servers


def test_check_items_names_close_variants_of_taught_items():
    exclude = Exclusions(("play devil's advocate", "push back"), ("scrutiny",))
    reply = check_items_reply(exclude, {"expressions": ["play the devil's advocate", "on the fence"], "words": ["Scrutiny", "candor"]})
    assert reply == "Already taught, replace: play the devil's advocate; Scrutiny"
    assert check_items_reply(exclude, {"expressions": ["on the fence"], "words": []}) == "None of these were taught before."


def test_a_full_session_fits_the_schema_the_model_answers_in():
    jsonschema.validate(sample_content().model_dump(exclude={"vocabulary": {"__all__": {"image"}}}), SESSION_SCHEMA)


def test_the_app_skill_always_runs_and_host_skills_come_after_it():
    fake = FakeQuery(result(sample_content().model_dump()))
    generator_with(fake, skills=("stop-slop",)).generate("x")
    prompt, options = fake.calls[0]
    assert options.skills == [APP_SKILL, "stop-slop"]
    assert options.plugins == [{"type": "local", "path": str(PLUGIN_DIR)}]
    assert f"{APP_SKILL}, stop-slop" in prompt
    assert (PLUGIN_DIR / "skills" / "session-writing" / "SKILL.md").is_file()
