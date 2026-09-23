import json

from mcp.types import CallToolResult, TextContent

from app.mcp_client import payload


def text(value: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=value)])


def test_payload_prefers_structured_content_then_parses_the_text():
    assert payload(CallToolResult(content=[], structured_content={"a": 1})) == {"a": 1}
    assert payload(text('{"b": 2}')) == {"b": 2}
    assert payload(text("plain")) == "plain"


def test_payload_reads_the_whole_text_not_the_error_excerpt():
    long = {"data": ["x" * 40] * 30}  # well past the 500 characters an error message keeps
    assert payload(CallToolResult(content=[TextContent(type="text", text=json.dumps(long))])) == long
