import jsonschema
import pytest

from app.generation.exclusions import Exclusions
from app.generation.generator import (
    APP_SKILL,
    ARTICLE_SKILL,
    CHECK_ITEMS_RULE,
    PLUGIN_DIR,
    SESSION_SCHEMA,
    ClaudeGenerator,
    check_items_reply,
)
from app.generation.progress import Progress, Stage
from app.llm import GenerationError
from tests.conftest import sample_draft
from tests.fake_claude import FakeQuery, assistant, result, tool_use


def generator_with(fake: FakeQuery, **kwargs) -> ClaudeGenerator:
    gen = ClaudeGenerator(model="sonnet", **kwargs)
    object.__setattr__(gen.claude, "query", fake)
    return gen


def test_generate_validates_the_payload_and_reports_progress():
    fake = FakeQuery(assistant(tool_use("WebSearch")), assistant(tool_use("StructuredOutput")), result(sample_draft().model_dump()))
    seen = []
    content = generator_with(fake).generate("Digital twins", seen.append)
    assert content.article.title == "Twins at Work"
    assert seen == [Progress(Stage.SEARCHING, 1), Progress(Stage.FINALIZING, 1)]


def test_a_payload_that_fails_validation_raises():
    with pytest.raises(GenerationError, match="validation"):
        generator_with(FakeQuery(result({"topic": "x"}))).generate("x")


def test_past_items_go_to_a_check_tool_not_the_prompt():
    fake = FakeQuery(result(sample_draft().model_dump()))
    generator_with(fake).generate("x", exclude=Exclusions(("scrutiny",)))
    prompt, options = fake.calls[0]
    assert CHECK_ITEMS_RULE in prompt and "scrutiny" not in prompt
    assert "session" in options.mcp_servers
    assert "mcp__session__check_items" in options.allowed_tools


def test_no_check_tool_without_past_items():
    fake = FakeQuery(result(sample_draft().model_dump()))
    generator_with(fake).generate("x", exclude=Exclusions())
    prompt, options = fake.calls[0]
    assert CHECK_ITEMS_RULE not in prompt and "session" not in options.mcp_servers


def test_check_items_names_close_variants_of_taught_words():
    exclude = Exclusions(("scrutiny", "the status quo"))
    reply = check_items_reply(exclude, {"words": ["Scrutiny", "candor", "status quo"]})
    assert reply == "Already taught, replace: Scrutiny; status quo"
    assert check_items_reply(exclude, {"words": ["candor"]}) == "None of these were taught before."


def test_a_full_draft_fits_the_schema_the_model_answers_in():
    jsonschema.validate(sample_draft().model_dump(), SESSION_SCHEMA)


def test_the_prompt_asks_for_no_expressions():
    prompt = ClaudeGenerator(model="m").build_prompt("t", Exclusions(("scrutiny",)))
    assert "expression" not in prompt.lower() and "1. article" in prompt and "2. vocabulary" in prompt
    assert "expressions" not in SESSION_SCHEMA["properties"]


def test_only_the_apps_own_skills_run():
    import inspect

    fake = FakeQuery(result(sample_draft().model_dump()))
    generator_with(fake).generate("x")
    prompt, options = fake.calls[0]
    assert options.skills == [APP_SKILL, ARTICLE_SKILL]
    assert options.plugins == [{"type": "local", "path": str(PLUGIN_DIR)}]
    assert f"invoke the {APP_SKILL} skill" in prompt
    assert "skills" not in inspect.signature(ClaudeGenerator).parameters  # nothing comes from the host
    assert (PLUGIN_DIR / "skills" / "session-writing" / "SKILL.md").is_file()


def test_the_time_limit_leaves_room_for_a_five_minute_run():
    """An Opus xhigh run took 303.6s and died at a 300s limit, one tool call from done."""
    assert ClaudeGenerator(model="opus").claude.timeout_s == 600


def test_the_humanizer_rewrites_the_article_before_its_evidence_and_translation_are_copied():
    fake = FakeQuery(result(sample_draft().model_dump()))
    generator_with(fake).generate("x")
    prompt, options = fake.calls[0]
    assert ARTICLE_SKILL in options.skills
    humanize = prompt.index(f"run the {ARTICLE_SKILL} skill on the title and body")
    assert prompt.index("1. article") < humanize < prompt.index("Then write 3 discussion questions") < prompt.index("Then give translation")
    assert ARTICLE_SKILL not in prompt[: prompt.index("\n\n")]  # only the article, not every part of the session
    skill = PLUGIN_DIR / "skills" / "humanizer"
    assert (skill / "SKILL.md").read_text().startswith("---\nname: humanizer\n") and (skill / "LICENSE").is_file()


def test_the_article_brings_a_cover_and_one_more_source_image_and_always_a_scene_to_draw_instead():
    article = SESSION_SCHEMA["properties"]["article"]
    assert {"figures", "picture"} <= set(article["required"])
    assert article["properties"]["figures"]["maxItems"] == 2
    assert set(article["properties"]["figures"]["items"]["required"]) == {"after", "image_url", "page_url", "credit", "caption"}
    assert article["properties"]["figures"]["items"]["properties"]["after"]["minimum"] == 0  # 0: the cover
    assert set(article["properties"]["picture"]["required"]) == {"scene", "caption"}
    prompt = ClaudeGenerator(model="m").build_prompt("t")
    figures = prompt.index("Then give figures:")
    assert prompt.index("Then give translation") < figures < prompt.index("2. vocabulary")
    assert "firecrawl_scrape" in prompt[figures:] and "Never a logo" in prompt[figures:] and "after 0" in prompt[figures:]
    assert prompt.index("Always give picture") < prompt.index("2. vocabulary")

