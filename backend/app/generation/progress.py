"""Turn the run's messages into generation stages, what the model is doing, and tokens spent."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from urllib.parse import urlparse

from claude_agent_sdk import (
    AssistantMessage,
    Message,
    StreamEvent,
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
    activity: str = ""  # the tool call under way, in words; blank outside skills and searching
    input_tokens: int = 0
    output_tokens: int = 0
    pictures_done: int = 0
    pictures_total: int = 0


CHARS_PER_TOKEN = 4  # live estimate while a turn streams; the turn's usage replaces it
DELTA_TEXT = {"text_delta": "text", "input_json_delta": "partial_json", "thinking_delta": "thinking"}


def describe(block: ToolUseBlock) -> str:
    args = block.input or {}
    if block.name == "Skill":
        return f"Loading the {args.get('skill') or args.get('command') or ''} skill".replace("the  skill", "a skill")
    if "query" in args:
        return f'Searching "{args["query"]}"'
    if "url" in args:
        return f"Reading {urlparse(str(args['url'])).netloc or args['url']}"
    if block.name.endswith("check_items"):
        return "Checking picks against past sessions"
    return ""


class TokenMeter:
    """Tokens per API turn, keyed by message id. Stream events fill a turn as it runs; the
    finished message's usage overwrites it, so no turn counts twice."""

    def __init__(self) -> None:
        self._turns: dict[str, list[int]] = {}
        self._current = ""

    @property
    def input_tokens(self) -> int:
        return sum(t[0] for t in self._turns.values())

    @property
    def output_tokens(self) -> int:
        return sum(t[1] for t in self._turns.values())

    def event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message", {})
            self._current = message.get("id", "")
            self._turns[self._current] = [input_of(message.get("usage") or {}), 0]
        elif kind == "content_block_delta" and self._current in self._turns:
            delta = event.get("delta", {})
            chars = len(delta.get(DELTA_TEXT.get(delta.get("type"), ""), ""))
            self._turns[self._current][1] += chars // CHARS_PER_TOKEN
        elif kind == "message_delta" and self._current in self._turns:
            if out := (event.get("usage") or {}).get("output_tokens"):
                self._turns[self._current][1] = out

    def message(self, message: AssistantMessage) -> None:
        if message.usage and message.message_id:
            self._turns[message.message_id] = [input_of(message.usage), message.usage.get("output_tokens", 0)]


def input_of(usage: dict) -> int:
    return sum(usage.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


class StreamTracker:
    """Feed every message; emits a Progress whenever anything shown changes."""

    def __init__(self, on_progress: Callable[[Progress], None]) -> None:
        self._on_progress = on_progress
        self._stage = Stage.STARTING
        self._searches = 0
        self._activity = ""
        self._tokens = TokenMeter()

    @property
    def progress(self) -> Progress:
        return Progress(
            self._stage, self._searches, self._activity, self._tokens.input_tokens, self._tokens.output_tokens
        )

    def feed(self, message: Message) -> None:
        before = self.progress
        if isinstance(message, StreamEvent):
            self._tokens.event(message.event)
        elif isinstance(message, AssistantMessage):
            self._tokens.message(message)
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
            self._activity = "" if self._stage == Stage.FINALIZING else describe(block)
        elif isinstance(block, (TextBlock, ThinkingBlock)) and self._stage != Stage.FINALIZING:
            self._stage = Stage.WRITING
            self._activity = ""


def with_pictures(progress: Progress, done: int, total: int) -> Progress:
    return replace(progress, stage=Stage.ILLUSTRATING, activity="", pictures_done=done, pictures_total=total)
