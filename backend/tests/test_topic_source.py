import httpx2
import pytest

from app import net
from app.llm import GenerationError
from app.net import HttpError
from app.topics.daily import ClaudeTopicSource
from app.topics.feeds import FEEDS, read_headlines, titles_in

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>The outlet itself</title>
<item><title>  First &amp; biggest story
</title></item><item><description>no title here</description></item><item><title><![CDATA[Second story]]></title></item>
</channel></rss>"""


class FakeClaude:
    def __init__(self, found):
        self.found = found
        self.prompts = []

    def run(self, prompt, schema, on_message=None):
        self.prompts.append(prompt)
        return self.found


def source_with(found, headlines=("[BBC] A headline", "[Yonhap] A Korean headline")):
    source = ClaudeTopicSource(read=lambda: list(headlines))
    source._claude = FakeClaude(found)
    return source


def test_titles_are_the_stories_in_their_order_and_not_the_channel():
    assert titles_in(RSS) == ["First & biggest story", "Second story"]


def test_a_feed_gives_at_most_so_many_titles():
    items = b"".join(b"<item><title>t%d</title></item>" % i for i in range(40))
    assert len(titles_in(b"<rss><channel>" + items + b"</channel></rss>")) == 25


def test_headlines_are_marked_with_their_outlet():
    lines = read_headlines(lambda url: RSS)
    assert f"[{next(iter(FEEDS))}] First & biggest story" in lines
    assert len(lines) == 2 * len(FEEDS)


def test_one_feed_failing_leaves_the_others():
    broken = next(iter(FEEDS.values()))

    def read(url):
        if url == broken:
            raise HttpError(502, "no route")
        return RSS

    assert len(read_headlines(read)) == 2 * (len(FEEDS) - 1)


def test_garbage_from_one_feed_leaves_the_others():
    broken = next(iter(FEEDS.values()))
    lines = read_headlines(lambda url: b"<html><oops" if url == broken else RSS)
    assert len(lines) == 2 * (len(FEEDS) - 1)


def test_a_feed_that_has_moved_is_followed(monkeypatch):
    def moved_once(request):
        if request.url.path.endswith("/new"):
            return httpx2.Response(200, content=RSS)
        return httpx2.Response(301, headers={"location": str(request.url.join("/new"))})

    monkeypatch.setattr(net, "TRANSPORT", httpx2.MockTransport(moved_once))
    assert len(read_headlines()) == 2 * len(FEEDS)


def test_the_source_gives_claude_the_headlines_and_no_tools():
    source = source_with({"korea": [], "world": []})
    source.fetch(15, [])
    assert "[BBC] A headline" in source._claude.prompts[0]
    assert ClaudeTopicSource()._claude.tools == () and ClaudeTopicSource()._claude.mcp == ()


def test_the_source_asks_for_a_korean_story_in_every_three():
    source = source_with({"korea": [], "world": []})
    source.fetch(15, [])
    assert "5 from the Korean outlets" in source._claude.prompts[0]
    assert "10 from the rest" in source._claude.prompts[0]


def test_the_stories_come_back_so_that_each_three_opens_with_a_korean_one():
    source = source_with({"korea": ["k1", "k2"], "world": ["w1", "w2", "w3", "w4", "w5"]})
    assert source.fetch(15, []) == ["k1", "w1", "w2", "k2", "w3", "w4", "w5"]


def test_blank_stories_are_dropped_and_the_rest_trimmed():
    source = source_with({"korea": ["  k1 ", " "], "world": ["w1", ""]})
    assert source.fetch(15, []) == ["k1", "w1"]


def test_the_source_tells_claude_what_was_already_used_today():
    source = source_with({"korea": [], "world": []})
    source.fetch(15, ["An old story"])
    assert "An old story" in source._claude.prompts[0]


def test_no_feed_answering_is_a_failure_and_asks_claude_nothing():
    source = source_with({"korea": [], "world": []}, headlines=())
    with pytest.raises(GenerationError, match="no news feed"):
        source.fetch(15, [])
    assert source._claude.prompts == []


def test_the_prompt_has_no_stray_braces_left_by_a_headline():
    source = source_with({"korea": [], "world": []}, headlines=("[BBC] A {curly} headline",))
    source.fetch(15, ["An {old} story"])
    assert "{curly}" in source._claude.prompts[0] and "{old}" in source._claude.prompts[0]
