"""Structured text runs of Claude through the Agent SDK. The SDK bundles the
Claude Code CLI, which signs in with CLAUDE_CODE_OAUTH_TOKEN (`claude
setup-token`), so the runs bill the Claude subscription. Every caller (session generator, topic
fetcher, feedback, phrasing, scenes) goes through `Claude.run`."""

import asyncio
import logging
from contextlib import aclosing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKError,
    Message,
    ResultMessage,
    query,
)

log = logging.getLogger(__name__)

OnMessage = Callable[[Message], None]


class GenerationError(Exception):
    pass


@dataclass(frozen=True)
class McpServer:
    """One MCP server a run may call (HTTP, or an in-process SDK server) and the tools allowed on it."""

    name: str
    config: Any
    tools: tuple[str, ...]


def firecrawl(key: str = "") -> McpServer:
    """Firecrawl's search MCP. Without a key it still answers, rate limited; a key lifts the limits."""
    config: dict = {"type": "http", "url": FIRECRAWL_URL}
    if key:
        config["headers"] = {"Authorization": f"Bearer {key}"}
    return McpServer("firecrawl", config, FIRECRAWL_TOOLS)


WEB_TOOLS = ("WebSearch", "WebFetch")
FIRECRAWL_URL = "https://mcp.firecrawl.dev/v2/mcp"
FIRECRAWL_TOOLS = ("mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_scrape")


class Runner(Protocol):
    """What the callers need from Claude; tests pass a fake."""

    def run(self, prompt: str, schema: dict, on_message: OnMessage | None = None) -> dict: ...


@dataclass(frozen=True)
class Claude:
    model: str
    effort: str | None = "low"  # None: the model takes no effort level
    timeout_s: float = 90
    tools: tuple[str, ...] = ()  # built-in tools; none by default
    mcp: tuple[McpServer, ...] = ()
    skills: tuple[str, ...] = ()
    plugins: tuple[str, ...] = ()  # local plugin folders, e.g. the app's own skills
    partial: bool = False  # stream token deltas too, for live progress
    query: Callable = field(default=query, repr=False)

    def options(self, schema: dict, extra: tuple[McpServer, ...] = ()) -> ClaudeAgentOptions:
        servers = self.mcp + extra
        return ClaudeAgentOptions(
            model=self.model,
            effort=self.effort,
            tools=[*self.tools, *(["Skill"] if self.skills else [])],  # `skills` only pre-approves the tool
            allowed_tools=[*self.tools, *(t for s in servers for t in s.tools)],
            mcp_servers={s.name: s.config for s in servers},
            strict_mcp_config=True,
            skills=list(self.skills) or None,
            plugins=[{"type": "local", "path": p} for p in self.plugins],
            output_format={"type": "json_schema", "schema": schema},
            include_partial_messages=self.partial,
        )

    def run(
        self, prompt: str, schema: dict, on_message: OnMessage | None = None, extra: tuple[McpServer, ...] = ()
    ) -> dict:
        """The structured output of one run. Raises GenerationError for every failure."""
        try:
            result = asyncio.run(self._run(prompt, self.options(schema, extra), on_message))
        except TimeoutError as e:
            raise GenerationError(f"claude timed out after {self.timeout_s:.0f}s") from e
        except ClaudeSDKError as e:
            raise GenerationError(f"claude failed: {e}") from e
        if result is None:
            raise GenerationError("claude produced no result")
        if result.is_error:
            raise GenerationError(result.result or "; ".join(result.errors or []) or result.subtype)
        if result.structured_output is None:
            raise GenerationError("claude returned no structured output")
        log.info(
            "%s run: %.1fs, %d turns, $%.3f", self.model, result.duration_ms / 1000, result.num_turns, result.total_cost_usd or 0
        )
        return result.structured_output

    async def _run(self, prompt: str, options: ClaudeAgentOptions, on_message: OnMessage | None) -> ResultMessage | None:
        """An error from `on_message` (a cancel) leaves the loop and closes the stream before it
        rises; raised inside the loop, it made the SDK's cleanup fail on a generator still running."""
        result = None
        stopped: Exception | None = None
        async with asyncio.timeout(self.timeout_s), aclosing(self.query(prompt=prompt, options=options)) as stream:
            async for message in stream:
                if isinstance(message, ResultMessage):
                    result = message
                try:
                    if on_message:
                        on_message(message)
                except Exception as e:
                    stopped = e
                    break
        if stopped:
            raise stopped
        return result
