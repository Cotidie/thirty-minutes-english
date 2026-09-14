from app.progress import Progress, Stage, StreamTracker


def assistant(*blocks: dict) -> dict:
    return {"type": "assistant", "message": {"content": list(blocks)}}


def tool_use(name: str) -> dict:
    return {"type": "tool_use", "name": name, "input": {}}


def test_tracks_skill_search_writing_and_finalizing_in_order():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed({"type": "system", "subtype": "init"})
    t.feed(assistant(tool_use("Skill")))
    t.feed(assistant(tool_use("mcp__firecrawl__firecrawl_search")))
    t.feed(assistant(tool_use("mcp__firecrawl__firecrawl_search")))
    t.feed(assistant({"type": "thinking", "thinking": ""}))
    t.feed(assistant(tool_use("StructuredOutput")))
    t.feed({"type": "result", "subtype": "success"})
    assert seen == [
        Progress(Stage.SKILLS, 0),
        Progress(Stage.SEARCHING, 1),
        Progress(Stage.SEARCHING, 2),
        Progress(Stage.WRITING, 2),
        Progress(Stage.FINALIZING, 2),
    ]


def test_ignores_events_that_change_nothing():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed({"type": "user", "message": {"content": []}})
    t.feed(assistant({"type": "thinking", "thinking": ""}))
    t.feed(assistant({"type": "text", "text": "..."}))
    assert seen == [Progress(Stage.WRITING, 0)]


def test_text_after_finalizing_does_not_regress():
    t = StreamTracker(lambda _: None)
    t.feed(assistant(tool_use("StructuredOutput")))
    t.feed(assistant({"type": "text", "text": "done"}))
    assert t.progress.stage == Stage.FINALIZING


def test_builtin_web_search_counts_as_a_search():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.feed(assistant(tool_use("WebSearch")))
    t.feed(assistant(tool_use("WebFetch")))
    assert seen == [Progress(Stage.SEARCHING, 1), Progress(Stage.SEARCHING, 2)]
