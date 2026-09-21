import json

from app.mcp_client import oauth_token, payload


def test_oauth_token_finds_the_login_by_server_url(tmp_path):
    creds = tmp_path / "c.json"
    creds.write_text(json.dumps({"mcpOAuth": {
        "comfy-cloud|abc": {"serverUrl": "https://cloud.comfy.org/mcp", "accessToken": "tok-comfy"},
        "notion|def": {"serverUrl": "https://mcp.notion.com/mcp", "accessToken": "tok-notion"},
    }}))
    assert oauth_token("https://cloud.comfy.org/mcp", creds) == "tok-comfy"
    assert oauth_token("https://mcp.openrouter.ai/mcp", creds) is None
    assert oauth_token("https://cloud.comfy.org/mcp", tmp_path / "missing.json") is None


def test_payload_prefers_structured_content_then_parses_the_text():
    assert payload({"structuredContent": {"a": 1}, "content": []}) == {"a": 1}
    assert payload({"content": [{"type": "text", "text": "{\"b\": 2}"}]}) == {"b": 2}
    assert payload({"content": [{"type": "text", "text": "plain"}]}) == "plain"
