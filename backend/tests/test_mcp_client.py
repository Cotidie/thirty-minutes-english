from app.mcp_client import Response, _message, payload


def test_payload_prefers_structured_content_then_parses_the_text():
    assert payload({"structuredContent": {"a": 1}, "content": []}) == {"a": 1}
    assert payload({"content": [{"type": "text", "text": "{\"b\": 2}"}]}) == {"b": 2}
    assert payload({"content": [{"type": "text", "text": "plain"}]}) == "plain"


def test_message_reads_plain_json_or_the_last_sse_event():
    assert _message(Response("application/json", None, '{"result": {"x": 1}}')) == {"result": {"x": 1}}
    sse = 'event: message\ndata: {"result": {"x": 1}}\n\ndata: {"result": {"x": 2}}\n'
    assert _message(Response("text/event-stream", "s1", sse)) == {"result": {"x": 2}}
    assert _message(Response("application/json", None, "")) == {}
