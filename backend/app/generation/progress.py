"""Turn the run's messages into coarse generation stages."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from claude_agent_sdk import (
    AssistantMessage,
    Message,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from app.llm import FIRECRAWL_TOOLS, WEB_TOOLS


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
    """Feed every message; emits a Progress whenever the stage or search count changes."""

    def __init__(self, on_progress: Callable[[Progress], None]) -> None:
        self._on_progress = on_progress
        self._stage = Stage.STARTING
        self._searches = 0

    @property
    def progress(self) -> Progress:
        return Progress(self._stage, self._searches)

    def feed(self, message: Message) -> None:
        if not isinstance(message, AssistantMessage):
            return
        before = self.progress
        for block in message.content:
            self._apply(block)
        if self.progress != before:
            self._on_progress(self.progress)

    def _apply(self, block) -> None:
        if isinstance(block, ToolUseBlock):
            if block.name == "Skill":
                self._stage = Stage.SKILLS
            elif block.name in WEB_TOOLS or block.name in FIRECRAWL_TOOLS:
                self._searches += 1
                self._stage = Stage.SEARCHING
            elif block.name == "StructuredOutput":
                self._stage = Stage.FINALIZING
        elif isinstance(block, (TextBlock, ThinkingBlock)) and self._stage != Stage.FINALIZING:
            self._stage = Stage.WRITING
