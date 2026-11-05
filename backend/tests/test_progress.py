from claude_agent_sdk import SystemMessage, ThinkingBlock

from app.generation.progress import Progress, Stage, StreamTracker, with_pictures
from tests.fake_claude import assistant, result, stream, text, tool_use


def stages(seen: list[Progress]) -> list[tuple[Stage, int]]:
    return [(p.stage, p.searches) for p in seen]


def test_the_first_pass_tracks_skills_searches_and_drafting_and_its_output_does_not_finalize():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed(SystemMessage(subtype="init", data={}))
    t.feed(assistant(tool_use("Skill")))
    t.feed(assistant(tool_use("WebSearch")))
    t.feed(assistant(tool_use("WebSearch")))
    t.feed(assistant(ThinkingBlock(thinking="", signature="")))
    t.feed(assistant(tool_use("StructuredOutput")))
    t.feed(result({}))
    assert stages(seen) == [
        (Stage.SKILLS, 0),
        (Stage.SEARCHING, 1),
        (Stage.SEARCHING, 2),
        (Stage.DRAFTING, 2),
    ]


def test_ignores_messages_that_change_nothing():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed(assistant(ThinkingBlock(thinking="", signature="")))
    t.feed(assistant(text()))
    assert seen == [Progress(Stage.DRAFTING, 0)]


def test_the_item_check_is_not_a_search_and_text_after_finalizing_does_not_regress():
    t = StreamTracker(lambda _: None)
    t.begin(Stage.FINISHING)
    t.feed(assistant(tool_use("mcp__session__check_items")))
    assert t.progress == Progress(Stage.FINISHING, 0, "Checking picks against past sessions")
    t.feed(assistant(tool_use("StructuredOutput")))
    t.feed(assistant(text("done")))
    assert t.progress.stage == Stage.FINALIZING


def test_builtin_web_tools_and_firecrawl_count_as_searches():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed(assistant(tool_use("WebSearch")))
    t.feed(assistant(tool_use("WebFetch")))
    t.feed(assistant(tool_use("mcp__firecrawl__firecrawl_search")))
    assert stages(seen) == [(Stage.SEARCHING, 1), (Stage.SEARCHING, 2), (Stage.SEARCHING, 3)]


def test_activity_names_the_query_the_page_and_the_skill():
    t = StreamTracker(lambda _: None)
    t.feed(assistant(tool_use("Skill", skill="english-session:session-writing")))
    assert t.progress.activity == "Loading the session-writing skill"
    t.feed(assistant(tool_use("mcp__firecrawl__firecrawl_search", query="preprint peer review")))
    assert t.progress.activity == 'Searching "preprint peer review"'
    t.feed(assistant(tool_use("WebFetch", url="https://www.nature.com/articles/x")))
    assert t.progress.activity == "Reading www.nature.com"
    t.feed(assistant(text()))
    assert t.progress.activity == ""


def test_tokens_count_each_turn_once_and_stream_deltas_live():
    t = StreamTracker(lambda _: None)
    usage = {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 50}
    t.feed(assistant(tool_use("WebSearch"), usage=usage, message_id="m1"))
    t.feed(assistant(text(), usage=usage, message_id="m1"))  # same turn, another block
    assert (t.progress.input_tokens, t.progress.output_tokens) == (100, 50)

    t.feed(stream({"type": "message_start", "message": {"id": "m2", "usage": {"input_tokens": 200}}}))
    t.feed(stream({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x" * 40}}))
    assert (t.progress.input_tokens, t.progress.output_tokens) == (300, 60)
    t.feed(stream({"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "y" * 80}}))
    assert t.progress.output_tokens == 80
    t.feed(assistant(text(), usage={"input_tokens": 200, "output_tokens": 33}, message_id="m2"))
    assert t.progress.output_tokens == 83  # the exact count replaces the estimate


def test_pictures_move_the_stage_to_illustrating_and_keep_the_tokens():
    p = with_pictures(Progress(Stage.FINALIZING, 3, "x", 100, 50), 2, 8)
    assert p == Progress(Stage.ILLUSTRATING, 3, "", 100, 50, 2, 8)


def test_a_block_that_starts_streaming_updates_the_label_at_once():
    t = StreamTracker(lambda _: None)
    t.begin(Stage.FINISHING)
    t.feed(assistant(tool_use("mcp__session__check_items")))
    assert t.progress.activity == "Checking picks against past sessions"
    t.feed(stream({"type": "content_block_start", "content_block": {"type": "thinking"}}))
    assert (t.progress.stage, t.progress.activity) == (Stage.FINISHING, "Thinking")
    t.feed(stream({"type": "content_block_start", "content_block": {"type": "tool_use", "name": "StructuredOutput"}}))
    assert t.progress.activity == "Writing out the session"
    t.feed(assistant(tool_use("StructuredOutput")))
    assert (t.progress.stage, t.progress.activity) == (Stage.FINALIZING, "")


def test_later_passes_hold_their_stage_and_only_the_finishing_output_finalizes():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.begin(Stage.EDITING)
    t.feed(assistant(tool_use("Skill", skill="english-session:stop-slop")))
    assert (t.progress.stage, t.progress.activity) == (Stage.EDITING, "Loading the stop-slop skill")
    t.feed(assistant(text()))
    t.feed(assistant(tool_use("StructuredOutput")))
    t.begin(Stage.FINISHING)
    t.feed(assistant(tool_use("StructuredOutput")))
    assert stages(seen) == [(Stage.EDITING, 0), (Stage.EDITING, 0), (Stage.EDITING, 0), (Stage.FINISHING, 0), (Stage.FINALIZING, 0)]


def test_a_pass_activity_shows_between_thoughts():
    t = StreamTracker(lambda _: None)
    t.begin(Stage.EDITING, "Fixing sentence and paragraph lengths")
    t.feed(stream({"type": "content_block_start", "content_block": {"type": "thinking"}}))
    assert t.progress.activity == "Thinking"
    t.feed(assistant(text()))
    assert (t.progress.stage, t.progress.activity) == (Stage.EDITING, "Fixing sentence and paragraph lengths")


def test_tokens_add_up_across_passes():
    t = StreamTracker(lambda _: None)
    t.feed(assistant(text(), usage={"input_tokens": 100, "output_tokens": 10}, message_id="m1"))
    t.begin(Stage.EDITING)
    t.feed(assistant(text(), usage={"input_tokens": 50, "output_tokens": 5}, message_id="m2"))
    assert (t.progress.input_tokens, t.progress.output_tokens) == (150, 15)
