"""A small client for an HTTP MCP server, signed in with a bearer token (an API
key). One session per client: initialize, then tools/call as needed, from any thread."""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from threading import Lock
from typing import Any

PROTOCOL = "2025-06-18"


class McpError(Exception):
    pass


@dataclass(frozen=True)
class Response:
    content_type: str
    session_id: str | None
    text: str


class McpClient:
    def __init__(self, url: str, token: str, timeout_s: float = 180) -> None:
        self._url = url
        self._token = token
        self._timeout_s = timeout_s
        self._session: str | None = None
        self._next_id = 0
        self._lock = Lock()

    def call(self, tool: str, arguments: dict) -> dict:
        """The tool's result object (`content`, and `structuredContent` when the server gives one).
        Raises McpError on a transport failure or a tool error."""
        with self._lock:
            if self._session is None:
                self._initialize()
        result = self._request("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            raise McpError(f"{tool}: {_text(result)}")
        return result

    def tools(self) -> list[dict]:
        """The server's tool list, with input schemas."""
        with self._lock:
            if self._session is None:
                self._initialize()
        return self._request("tools/list", {}).get("tools", [])

    def _initialize(self) -> None:
        params = {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "english-speaking-claude", "version": "1"}}
        response = self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": params})
        self._session = response.session_id
        _check(_message(response), "initialize")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
        response = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return _check(_message(response), method)

    def _post(self, body: dict) -> Response:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL,
            "User-Agent": "english-speaking-claude/1",  # Cloudflare turns the urllib default away
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        request = urllib.request.Request(self._url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as raw:
                return Response(raw.headers.get("content-type", ""), raw.headers.get("mcp-session-id"), raw.read().decode())
        except urllib.error.HTTPError as e:
            raise McpError(f"{self._url}: HTTP {e.code} {e.read()[:200]!r}") from e
        except (urllib.error.URLError, OSError) as e:
            raise McpError(f"{self._url}: {e}") from e


def _check(message: dict, method: str) -> dict:
    if "error" in message:
        raise McpError(f"{method}: {message['error'].get('message', message['error'])}")
    return message.get("result", {})


def _message(response: Response) -> dict:
    """The JSON-RPC message in a plain JSON body, or the last `data:` event of an SSE body."""
    if response.content_type.startswith("text/event-stream"):
        message: dict = {}
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    message = json.loads(line[5:].strip())
                except ValueError:
                    continue
        return message
    return json.loads(response.text) if response.text.strip() else {}


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
