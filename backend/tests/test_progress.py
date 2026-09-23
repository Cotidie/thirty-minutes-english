from claude_agent_sdk import SystemMessage, ThinkingBlock

from app.generation.progress import Progress, Stage, StreamTracker
from tests.fake_claude import assistant, result, text, tool_use


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
    assert seen == [
        Progress(Stage.SKILLS, 0),
        Progress(Stage.SEARCHING, 1),
        Progress(Stage.SEARCHING, 2),
        Progress(Stage.WRITING, 2),
        Progress(Stage.FINALIZING, 2),
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
    assert t.progress == Progress(Stage.STARTING, 0)
    t.feed(assistant(tool_use("StructuredOutput")))
    t.feed(assistant(text("done")))
    assert t.progress.stage == Stage.FINALIZING


def test_builtin_web_search_counts_as_a_search():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed(assistant(tool_use("WebSearch")))
    t.feed(assistant(tool_use("WebFetch")))
    assert seen == [Progress(Stage.SEARCHING, 1), Progress(Stage.SEARCHING, 2)]


def test_a_firecrawl_search_counts_as_a_search():
    seen: list[Progress] = []
    StreamTracker(seen.append).feed(assistant(tool_use("mcp__firecrawl__firecrawl_search")))
    assert seen == [Progress(Stage.SEARCHING, 1)]
