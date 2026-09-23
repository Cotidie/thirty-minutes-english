from claude_agent_sdk import SystemMessage, ThinkingBlock

from app.generation.progress import Progress, Stage, StreamTracker, with_pictures
from tests.fake_claude import assistant, result, stream, text, tool_use


def stages(seen: list[Progress]) -> list[tuple[Stage, int]]:
    return [(p.stage, p.searches) for p in seen]


def test_tracks_skill_search_writing_and_finalizing_in_order():
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
        (Stage.WRITING, 2),
        (Stage.FINALIZING, 2),
    ]


def test_ignores_messages_that_change_nothing():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed(assistant(ThinkingBlock(thinking="", signature="")))
    t.feed(assistant(text()))
    assert seen == [Progress(Stage.WRITING, 0)]


def test_the_item_check_is_not_a_search_and_text_after_finalizing_does_not_regress():
    t = StreamTracker(lambda _: None)
    t.feed(assistant(tool_use("mcp__session__check_items")))
    assert t.progress == Progress(Stage.STARTING, 0, "Checking picks against past sessions")
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
