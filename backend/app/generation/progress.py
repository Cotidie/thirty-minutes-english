"""Turn claude's stream-json events into coarse generation stages."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class Stage(StrEnum):
    STARTING = "starting"
    SKILLS = "skills"
    SEARCHING = "searching"
    WRITING = "writing"
    FINALIZING = "finalizing"
    ILLUSTRATING = "illustrating"  # pictures for the words, after the text is done


@dataclass(frozen=True)
class Progress:
    stage: Stage
    searches: int = 0


class StreamTracker:
    """Feed every stream-json event; emits a Progress whenever the stage or search count changes."""

    def __init__(self, on_progress: Callable[[Progress], None]) -> None:
        self._on_progress = on_progress
        self._stage = Stage.STARTING
        self._searches = 0

    @property
    def progress(self) -> Progress:
        return Progress(self._stage, self._searches)

    def feed(self, event: dict) -> None:
        if event.get("type") != "assistant":
            return
        before = self.progress
        for block in event.get("message", {}).get("content", []):
            self._apply(block)
        if self.progress != before:
            self._on_progress(self.progress)

    def _apply(self, block: dict) -> None:
        kind = block.get("type")
        if kind == "tool_use":
            name = block.get("name", "")
            if name == "Skill":
                self._stage = Stage.SKILLS
            elif name.startswith("mcp__") or name in ("WebSearch", "WebFetch"):
                self._searches += 1
                self._stage = Stage.SEARCHING
            elif name == "StructuredOutput":
                self._stage = Stage.FINALIZING
        elif kind in ("text", "thinking") and self._stage != Stage.FINALIZING:
            self._stage = Stage.WRITING
