"""Where a fluent reader pauses in a paragraph: thought-group boundaries as word
indices, from a text run of the claude CLI with the prompt in the read-aloud
folder. The answer is checked word for word against the paragraph."""

import re
from pathlib import Path
from typing import Protocol

from app.claude_cli import ClaudeCli, GenerationError, structured_output

PHRASING_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["marked"],
    "properties": {"marked": {"type": "string"}},
}

SLASH = re.compile(r"\s*/\s*")


class Runner(Protocol):
    def run(self, prompt: str, schema: dict, on_event=None) -> dict: ...


class PhrasingMarker:
    def __init__(self, cli: Runner, agent_dir: Path) -> None:
        self._cli = cli
        self._template = (agent_dir / "prompts" / "phrasing.md").read_text()

    @classmethod
    def with_cli(cls, agent_dir: Path, model: str, effort: str = "low") -> "PhrasingMarker":
        return cls(ClaudeCli(model=model, effort=effort, tools=(), mcp_config=None, timeout_s=90), agent_dir)

    def build_prompt(self, paragraph: str) -> str:
        return self._template.replace("{{paragraph}}", paragraph)

    def mark(self, paragraph: str) -> list[int]:
        """Indices of the words that open a new thought group (never 0). Raises GenerationError."""
        envelope = self._cli.run(self.build_prompt(paragraph), PHRASING_SCHEMA)
        marked = str(structured_output(envelope).get("marked", ""))
        return breaks_in(marked, paragraph)


def breaks_in(marked: str, paragraph: str) -> list[int]:
    """Word indices the slashes sit before, once `marked` is checked against `paragraph`."""
    groups = [g.split() for g in SLASH.split(marked) if g.strip()]
    words = [w for g in groups for w in g]
    if words != paragraph.split():
        raise GenerationError("phrasing did not match the paragraph word for word")
    breaks: list[int] = []
    at = 0
    for group in groups[:-1]:
        at += len(group)
        breaks.append(at)
    return breaks
