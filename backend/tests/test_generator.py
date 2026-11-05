import pytest

from app.generation.exclusions import Exclusions
from app.generation.generator import PLUGIN_DIR, ClaudeGenerator, check_items_reply
from app.generation.jobs import Cancelled
from app.generation.progress import Progress, Stage
from app.generation.prompts import APP_SKILL, CHECK_ITEMS_RULE, HUMANIZER_SKILL, REPAIR_ACTIVITY, STOP_SLOP_SKILL
from app.llm import GenerationError
from tests.conftest import readable_body, sample_finish, sample_first_draft
from tests.fake_claude import ScriptedQuery, assistant, result, stream, text, tool_use

LONG = " ".join(["Long"] + ["word"] * 24) + "."  # 25 words, over the limit
POLISHED_WITH_A_LONG_SENTENCE = readable_body("polished").replace("Polished", LONG + " Polished", 1)


def generator_with(fake, **kwargs) -> ClaudeGenerator:
    gen = ClaudeGenerator(model="sonnet", **kwargs)
    for claude in (gen.drafter, gen.editor, gen.polisher, gen.finisher):
        object.__setattr__(claude, "query", fake)
    return gen


def passes(*, draft=None, edit=None, polish=None, repair=None, finish=None) -> ScriptedQuery:
    """One script per call, in order; `repair` only when given."""
    scripts = [
        draft or (result(sample_first_draft()),),
        edit or (result({"title": "Twins at Work", "body": readable_body("edited")}),),
        polish or (result({"title": "Twins at Work", "body": readable_body("polished")}),),
        *([repair] if repair else []),
        finish or (result(sample_finish()),),
    ]
    return ScriptedQuery(*scripts)


def test_the_article_goes_through_draft_edit_polish_and_finish_in_order():
    fake = passes()
    draft = generator_with(fake).generate("Digital twins")
    prompts = [prompt for prompt, _ in fake.calls]
    assert len(prompts) == 4
    assert "Today's article topic: Digital twins" in prompts[0]
    assert readable_body("draft") in prompts[1] and readable_body("edited") in prompts[2] and readable_body("polished") in prompts[3]
    assert draft.article.body == readable_body("polished") and draft.article.sources[0].url == "https://example.com"
    assert "session" not in fake.calls[3][1].mcp_servers  # no past words, no check tool


def test_each_pass_runs_with_its_own_tools_and_skills():
    fake = passes()
    generator_with(fake).generate("x", exclude=Exclusions(("scrutiny",)))
    (_, drafting), (_, editing), (_, polishing), (finishing_prompt, finishing) = fake.calls
    assert drafting.skills == [APP_SKILL] and "WebSearch" in drafting.allowed_tools and "firecrawl" in drafting.mcp_servers
    assert (editing.tools, editing.allowed_tools, editing.mcp_servers, editing.skills) == ([], [], {}, None)
    assert polishing.skills == [HUMANIZER_SKILL, STOP_SLOP_SKILL] and polishing.tools == ["Read", "Skill"]
    assert finishing.skills == [APP_SKILL] and "session" in finishing.mcp_servers and "session" not in drafting.mcp_servers
    assert CHECK_ITEMS_RULE in finishing_prompt and "scrutiny" not in finishing_prompt
    assert all(o.plugins == [{"type": "local", "path": str(PLUGIN_DIR)}] for o in (drafting, polishing, finishing))


def test_every_pass_keeps_the_ten_minute_limit():
    gen = ClaudeGenerator(model="opus")
    assert {c.timeout_s for c in (gen.drafter, gen.editor, gen.polisher, gen.finisher)} == {600}


def test_check_items_names_close_variants_of_taught_words():
    exclude = Exclusions(("scrutiny", "the status quo"))
    reply = check_items_reply(exclude, {"words": ["Scrutiny", "candor", "status quo"]})
    assert reply == "Already taught, replace: Scrutiny; status quo"
    assert check_items_reply(exclude, {"words": ["candor"]}) == "None of these were taught before."


def test_a_long_sentence_gets_one_repair_that_names_it():
    fake = passes(
        polish=(result({"title": "t", "body": POLISHED_WITH_A_LONG_SENTENCE}),),
        repair=(result({"title": "t", "body": readable_body("repaired")}),),
    )
    draft = generator_with(fake).generate("x")
    assert len(fake.calls) == 5
    assert f'Sentence of 25 words (limit 20): "{LONG}"' in fake.calls[3][0]
    assert fake.calls[3][1].skills is None  # the repair runs on the editor
    assert draft.article.body == readable_body("repaired")


def test_a_repair_that_leaves_more_problems_is_set_aside():
    fake = passes(
        polish=(result({"title": "t", "body": POLISHED_WITH_A_LONG_SENTENCE}),),
        repair=(result({"title": "t", "body": "One.\n\nTwo.\n\nThree."}),),  # 4 problems against the polished 2
    )
    assert generator_with(fake).generate("x").article.body == POLISHED_WITH_A_LONG_SENTENCE


def test_a_failed_repair_keeps_the_polished_article_and_goes_on():
    fake = passes(
        polish=(result({"title": "t", "body": POLISHED_WITH_A_LONG_SENTENCE}),),
        repair=(result(is_error=True, text="overloaded"),),
    )
    draft = generator_with(fake).generate("x")
    assert draft.article.body == POLISHED_WITH_A_LONG_SENTENCE and len(fake.calls) == 5


def test_a_cancel_during_the_repair_is_not_swallowed():
    thinking = stream({"type": "content_block_start", "content_block": {"type": "thinking"}})
    fake = passes(
        polish=(result({"title": "t", "body": POLISHED_WITH_A_LONG_SENTENCE}),),
        repair=(thinking, result({"title": "t", "body": POLISHED_WITH_A_LONG_SENTENCE})),
    )
    seen: list[Progress] = []

    def cancel_in_repair(progress):
        """Lets the repair start, then cancels on its first message, inside the Claude run."""
        seen.append(progress)
        if any(p.activity == REPAIR_ACTIVITY for p in seen[:-1]):
            raise Cancelled

    with pytest.raises(Cancelled):
        generator_with(fake).generate("x", on_progress=cancel_in_repair)
    assert len(fake.calls) == 4


def test_a_failed_edit_fails_the_whole_generation():
    fake = passes(edit=(result(is_error=True, text="overloaded"),))
    with pytest.raises(GenerationError, match="overloaded"):
        generator_with(fake).generate("x")
    assert len(fake.calls) == 2


def test_a_draft_that_fails_validation_raises():
    with pytest.raises(GenerationError, match="validation"):
        generator_with(passes(draft=(result({"title": "x"}),))).generate("x")


def test_progress_runs_through_the_passes_in_order():
    fake = passes(draft=(assistant(tool_use("WebSearch")), assistant(text()), result(sample_first_draft())))
    seen: list[Progress] = []
    generator_with(fake).generate("x", seen.append)
    order = [p.stage for p in seen]
    assert [s for i, s in enumerate(order) if i == 0 or order[i - 1] != s] == [
        Stage.SEARCHING,
        Stage.DRAFTING,
        Stage.EDITING,
        Stage.POLISHING,
        Stage.FINISHING,
    ]
