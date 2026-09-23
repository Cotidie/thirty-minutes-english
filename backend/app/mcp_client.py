"""An HTTP MCP server reached through the official mcp SDK, signed in with an API key
as a bearer token (image providers, and the key check in Settings)."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

USER_AGENT = "english-speaking-claude/1"  # Cloudflare in front of OpenRouter's MCP turns the default away


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

    async def tools(self) -> list[str]:
        return [t.name for t in (await self._client.list_tools()).tools]


@dataclass(frozen=True)
class McpHttp:
    url: str
    key: str = ""
    read_timeout_s: float = 300

    @asynccontextmanager
    async def session(self) -> AsyncIterator[Session]:
        """Raises McpError for a refused key, an unreachable server, or a failed tool."""
        headers = {"User-Agent": USER_AGENT}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        http = httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30, read=self.read_timeout_s))
        try:
            async with Client(streamable_http_client(self.url, http_client=http)) as client:
                yield Session(client)
        except McpError:
            raise
        except Exception as e:
            raise McpError(f"{self.url}: {_root(e)}") from e
        finally:
            await http.aclose()

    def check(self) -> None:
        """Connects and lists the tools once; raises McpError when that fails."""

        async def connect() -> None:
            async with self.session() as session:
                await session.tools()

        asyncio.run(connect())


def _root(error: BaseException) -> str:
    """The first real cause inside the SDK's task-group wrapping."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    if isinstance(error, httpx2.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    return str(error) or type(error).__name__


def text_of(result: CallToolResult) -> str:
    return " ".join(block.text for block in result.content if block.type == "text")[:500]


def payload(result: CallToolResult) -> Any:
    """What a tool returned as data: its structured content, else its text parsed as JSON, else that text."""
    if result.structured_content is not None:
        return result.structured_content
    text = text_of(result)
    try:
        return json.loads(text)
    except ValueError:
        return text
