"""An HTTP MCP server reached through the official mcp SDK, signed in with an API key
as a bearer token (OpenRouter's image server)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

USER_AGENT = "english-speaking-claude/1"  # Cloudflare in front of OpenRouter's MCP turns the default away
READ_TIMEOUT_S = 300  # a picture can take minutes


class McpError(Exception):
    pass


class Session:
    """One connected session; calls may run side by side."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def call(self, tool: str, arguments: dict) -> CallToolResult:
        """Raises McpError when the tool reports an error."""
        result = await self._client.call_tool(tool, arguments)
        if result.is_error:
            raise McpError(f"{tool}: {text_of(result)}")
        return result


@dataclass(frozen=True)
class McpHttp:
    url: str
    key: str = ""

    @asynccontextmanager
    async def session(self) -> AsyncIterator[Session]:
        """Raises McpError for a refused key, an unreachable server, or a failed tool."""
        headers = {"User-Agent": USER_AGENT}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        http = httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30, read=READ_TIMEOUT_S))
        try:
            async with Client(streamable_http_client(self.url, http_client=http)) as client:
                yield Session(client)
        except McpError:
            raise
        except Exception as e:
            raise McpError(f"{self.url}: {_root(e)}") from e
        finally:
            await http.aclose()


def _root(error: BaseException) -> str:
    """The first real cause inside the SDK's task-group wrapping."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    if isinstance(error, httpx2.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    return str(error) or type(error).__name__


def text_of(result: CallToolResult) -> str:
    """The start of the text, short enough for an error message."""
    return " ".join(block.text for block in result.content if block.type == "text")[:500]
