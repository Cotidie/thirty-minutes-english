"""A session's text, written by Claude in passes: a researched draft, an edit for reading aloud, a polish
against machine-sounding prose, one repair if a length limit still breaks, then everything copied from
the final article (questions, translation, figures, pictures to draw) and the words."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

from claude_agent_sdk import create_sdk_mcp_server, tool
from pydantic import BaseModel

from app.generation.exclusions import Exclusions
from app.generation.levels import DEFAULT_LEVELS
from app.generation.passes import (
    DRAFT_SCHEMA,
    FINISH_SCHEMA,
    TEXT_SCHEMA,
    VOCABULARY_COUNT,  # noqa: F401  # imported from here by the job runner and tests
    ArticleText,
    Finish,
    FirstDraft,
    ImageCandidate,
    assemble,
    parse,
)
from app.generation.progress import Progress, Stage, StreamTracker
from app.generation.prompts import (
    APP_SKILL,
    HUMANIZER_SKILL,
    REPAIR_ACTIVITY,
    STOP_SLOP_SKILL,
    draft_prompt,
    edit_prompt,
    finish_prompt,
    polish_prompt,
    repair_prompt,
)
from app.generation.readability import problems
from app.llm import WEB_TOOLS, Claude, GenerationError, McpServer, firecrawl
from app.models import Draft

log = logging.getLogger(__name__)

OnProgress = Callable[[Progress], None]
M = TypeVar("M", bound=BaseModel)


class Generator(Protocol):
    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> Draft: ...


def check_items_reply(exclude: Exclusions, args: dict) -> str:
    taught = exclude.taught(args.get("words", []))
    return f"Already taught, replace: {'; '.join(taught)}" if taught else "None of these were taught before."


def check_items_server(exclude: Exclusions) -> McpServer:
    """An in-process tool the model checks its picks against, so the banned list stays out of the prompt."""

    @tool("check_items", "Which of these words earlier sessions already taught", {"words": list[str]})
    async def check_items(args: dict) -> dict:
        return {"content": [{"type": "text", "text": check_items_reply(exclude, args)}]}

    return McpServer("session", create_sdk_mcp_server("session", tools=[check_items]), ("mcp__session__check_items",))


# The app's own writing rules, a local plugin beside the app package (backend/plugin, /app/plugin in the image).
PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugin"


# The cutoff for a hung call, not a budget: Opus at xhigh took about 300s for a whole session in one call.
TIMEOUT_S = 600


class ClaudeGenerator:
    """Runs on the app's own skills only (backend/plugin), so a session reads the same on any machine.
    Every pass uses the same model and effort; each has only the tools and skills its job needs."""

    def __init__(
        self,
        model: str = "opus",
        effort: str | None = "xhigh",
        firecrawl_key: str = "",
        timeout_s: float = TIMEOUT_S,
        levels: tuple[str, ...] = DEFAULT_LEVELS,
    ) -> None:
        self.levels = levels
        plugins = (str(PLUGIN_DIR),)
        self.drafter = Claude(
            model, effort, timeout_s, tools=("Read", *WEB_TOOLS), mcp=(firecrawl(firecrawl_key),),
            skills=(APP_SKILL,), plugins=plugins, partial=True,
        )
        self.editor = Claude(model, effort, timeout_s, partial=True)  # the edit and the repair: text in, text out
        self.polisher = Claude(
            model, effort, timeout_s, tools=("Read",), skills=(HUMANIZER_SKILL, STOP_SLOP_SKILL), plugins=plugins, partial=True,
        )
        self.finisher = Claude(model, effort, timeout_s, tools=("Read",), skills=(APP_SKILL,), plugins=plugins, partial=True)

    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> Draft:
        tracker = StreamTracker(on_progress or (lambda _: None))
        first = self._draft(topic, tracker)
        edited = self._edit(first, tracker)
        polished = self._polish(edited, tracker)
        final = self._fix_lengths(polished, tracker)
        finish = self._finish(topic, final, first.images, exclude, tracker)
        return assemble(final, first, finish)

    def _draft(self, topic: str, tracker: StreamTracker) -> FirstDraft:
        """The tracker starts in this pass, so its first messages move it out of STARTING themselves."""
        return self._run("drafting", self.drafter, draft_prompt(topic), DRAFT_SCHEMA, FirstDraft, tracker)

    def _edit(self, text: ArticleText, tracker: StreamTracker) -> ArticleText:
        tracker.begin(Stage.EDITING)
        return self._run("editing", self.editor, edit_prompt(text), TEXT_SCHEMA, ArticleText, tracker)

    def _polish(self, text: ArticleText, tracker: StreamTracker) -> ArticleText:
        tracker.begin(Stage.POLISHING)
        return self._run("polishing", self.polisher, polish_prompt(text), TEXT_SCHEMA, ArticleText, tracker)

    def _fix_lengths(self, text: ArticleText, tracker: StreamTracker) -> ArticleText:
        """One repair when the polished article breaks a length limit. Whichever text breaks fewer goes on;
        a failed repair leaves the polished one, since a length is never worth failing the session over."""
        found = problems(text.body)
        if not found:
            log.info("readability: clean after polishing")
            return text
        try:
            repaired = self._repair(text, found, tracker)
        except GenerationError as e:
            log.warning("readability: repair failed, keeping the polished text (%d problems): %s", len(found), e)
            return text
        left = problems(repaired.body)
        log.info("readability: %d problems after polishing, %d after repair", len(found), len(left))
        kept, still = (repaired, left) if len(left) <= len(found) else (text, found)
        if still:
            log.warning("readability: still %s", still)
        return kept

    def _repair(self, text: ArticleText, found: list[str], tracker: StreamTracker) -> ArticleText:
        tracker.begin(Stage.POLISHING, REPAIR_ACTIVITY)
        return self._run("repair", self.editor, repair_prompt(text, found), TEXT_SCHEMA, ArticleText, tracker)

    def _finish(
        self, topic: str, text: ArticleText, images: list[ImageCandidate], exclude: Exclusions | None, tracker: StreamTracker
    ) -> Finish:
        tracker.begin(Stage.FINISHING)
        prompt = finish_prompt(topic, text, images, self.levels, check_items=bool(exclude))
        extra = (check_items_server(exclude),) if exclude else ()
        return self._run("finishing", self.finisher, prompt, FINISH_SCHEMA, Finish, tracker, extra)

    @staticmethod
    def _run(
        name: str,
        claude: Claude,
        prompt: str,
        schema: dict,
        model: type[M],
        tracker: StreamTracker,
        extra: tuple[McpServer, ...] = (),
    ) -> M:
        log.info("session pass: %s", name)
        return parse(model, claude.run(prompt, schema, tracker.feed, extra))
