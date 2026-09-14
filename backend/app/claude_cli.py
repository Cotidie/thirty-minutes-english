"""Running the local `claude` CLI as a subprocess and reading its stream-json.

Both the session generator and the daily topic fetcher go through here, so the
command shape, the timeout and the error wording live in one place.
"""

import json
import os
import subprocess
import threading
from collections.abc import Callable

FIRECRAWL_MCP: dict = {
    "mcpServers": {"firecrawl": {"type": "http", "url": "https://mcp.firecrawl.dev/v2/mcp-oauth"}}
}
BUILTIN_TOOLS = ("Skill", "Read")
WEB_TOOLS = ("mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_scrape")

OnEvent = Callable[[dict], None]


class GenerationError(Exception):
    pass


class ClaudeCli:
    def __init__(
        self,
        model: str = "opus",
        effort: str = "xhigh",
        mcp_config: dict = FIRECRAWL_MCP,
        timeout_s: float = 300,
    ) -> None:
        self.model = model
        self.effort = effort
        self.mcp_config = mcp_config
        self.timeout_s = timeout_s

    def build_command(self, schema: dict) -> list[str]:
        return [
            "claude",
            "-p",
            "--model",
            self.model,
            "--effort",
            self.effort,
            "--output-format",
            "stream-json",
            "--verbose",
            "--json-schema",
            json.dumps(schema),
            "--tools",
            ",".join(BUILTIN_TOOLS),
            "--allowedTools",
            ",".join(BUILTIN_TOOLS + WEB_TOOLS),
            "--setting-sources",
            "user",
            "--strict-mcp-config",
            "--mcp-config",
            json.dumps(self.mcp_config),
            "--no-session-persistence",
        ]

    def run(self, prompt: str, schema: dict, on_event: OnEvent | None = None) -> dict:
        """The result envelope of one run. Raises GenerationError for every failure."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            proc = subprocess.Popen(
                self.build_command(schema),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except FileNotFoundError as e:
            raise GenerationError("claude CLI not found on PATH") from e
        assert proc.stdin and proc.stdout and proc.stderr
        proc.stdin.write(prompt)
        proc.stdin.close()
        killer = threading.Timer(self.timeout_s, proc.kill)
        killer.start()
        result: dict | None = None
        try:
            for line in proc.stdout:
                event = _parse_event(line)
                if event is None:
                    continue
                if event.get("type") == "result":
                    result = event
                if on_event:
                    on_event(event)
            stderr = proc.stderr.read()
            proc.wait()
        finally:
            timed_out = not killer.is_alive()
            killer.cancel()
        if timed_out:
            raise GenerationError(f"claude timed out after {self.timeout_s:.0f}s")
        if proc.returncode != 0:
            raise GenerationError(f"claude exited {proc.returncode}: {stderr.strip()[-500:]}")
        if result is None:
            raise GenerationError("claude produced no result event")
        return result


def structured_output(envelope: dict) -> dict:
    if envelope.get("is_error"):
        raise GenerationError(str(envelope.get("result", "unknown error")))
    payload = envelope.get("structured_output")
    if payload is None:
        raise GenerationError("claude returned no structured output")
    return payload


def _parse_event(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
