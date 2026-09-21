"""A small client for an HTTP MCP server, signed in with the OAuth token the
claude CLI keeps in ~/.claude/.credentials.json (copied into the container).
One session per client: initialize, then tools/call as needed."""

import json
from pathlib import Path
from typing import Any

import httpx2 as httpx

PROTOCOL = "2025-06-18"


class McpError(Exception):
    pass


def oauth_token(server_url: str, credentials: Path | None = None) -> str | None:
    """The saved access token for `server_url`, or None when nobody has logged in to it."""
    path = credentials or Path.home() / ".claude" / ".credentials.json"
    try:
        entries = json.loads(path.read_text()).get("mcpOAuth", {})
    except (OSError, ValueError):
        return None
    for entry in entries.values():
        if entry.get("serverUrl") == server_url and entry.get("accessToken"):
            return entry["accessToken"]
    return None


class McpClient:
    def __init__(self, url: str, token: str, timeout_s: float = 120) -> None:
        self._url = url
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"},
            timeout=timeout_s,
        )
        self._session: str | None = None
        self._next_id = 0

    def call(self, tool: str, arguments: dict) -> dict:
        """The tool's result object (`content`, and `structuredContent` when the server gives one).
        Raises McpError on a transport failure or a tool error."""
        if self._session is None:
            self._initialize()
        result = self._request("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            raise McpError(f"{tool}: {_text(result)}")
        return result

    def close(self) -> None:
        self._http.close()

    def _initialize(self) -> None:
        params = {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "english-speaking-claude", "version": "1"}}
        self._request("initialize", params)
        self._notify("notifications/initialized")

    def _request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        response = self._post({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
        if method == "initialize":
            self._session = response.headers.get("mcp-session-id")
        message = _message(response)
        if "error" in message:
            raise McpError(f"{method}: {message['error'].get('message', message['error'])}")
        return message.get("result", {})

    def _notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})

    def _post(self, body: dict) -> httpx.Response:
        headers = {"MCP-Protocol-Version": PROTOCOL}
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        try:
            response = self._http.post(self._url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise McpError(f"{self._url}: {e}") from e
        if response.status_code >= 400:
            raise McpError(f"{self._url}: HTTP {response.status_code} {response.text[:200]}")
        return response


def _message(response: httpx.Response) -> dict:
    """The JSON-RPC message in a plain JSON body, or the last `data:` event of an SSE body."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        message: dict = {}
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    message = json.loads(line[5:].strip())
                except ValueError:
                    continue
        return message
    if not response.content:
        return {}
    return response.json()


def _text(result: dict) -> str:
    return " ".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")[:500]


def payload(result: dict) -> Any:
    """What a tool returned as data: its structuredContent, else its first text block parsed as JSON, else that text."""
    if "structuredContent" in result:
        return result["structuredContent"]
    text = _text(result)
    try:
        return json.loads(text)
    except ValueError:
        return text
