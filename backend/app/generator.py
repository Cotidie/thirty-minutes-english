import json
import os
import subprocess
import threading
from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from app.exclusions import Exclusions
from app.models import SessionContent
from app.progress import Progress, StreamTracker

OnProgress = Callable[[Progress], None]


class GenerationError(Exception):
    pass


class Generator(Protocol):
    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> SessionContent: ...


EXPRESSION_COUNT = 6
VOCABULARY_COUNT = 12

SESSION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic", "expressions", "article", "vocabulary"],
    "properties": {
        "topic": {"type": "string"},
        "expressions": {
            "type": "array",
            "minItems": EXPRESSION_COUNT,
            "maxItems": EXPRESSION_COUNT,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["phrase", "meaning", "usage_note", "examples"],
                "properties": {
                    "phrase": {"type": "string"},
                    "meaning": {"type": "string"},
                    "usage_note": {"type": "string"},
                    "examples": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}},
                },
            },
        },
        "article": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "body", "questions", "sources"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "sources": {
                    "type": "array",
                    "minItems": 0,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["title", "url"],
                        "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                    },
                },
                "questions": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["text", "evidence"],
                        "properties": {
                            "text": {"type": "string"},
                            "evidence": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}},
                        },
                    },
                },
            },
        },
        "vocabulary": {
            "type": "array",
            "minItems": VOCABULARY_COUNT,
            "maxItems": VOCABULARY_COUNT,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["word", "pos", "definition", "example"],
                "properties": {
                    "word": {"type": "string"},
                    "pos": {"type": "string"},
                    "definition": {"type": "string"},
                    "example": {"type": "string"},
                },
            },
        },
    },
}

PROMPT_TEMPLATE = """You are preparing material for a 30-minute English conversation practice session \
between two Korean graduate students at roughly B2 level who want to sound natural. Topics rotate across \
technology, literature, and world history; treat each as a general-interest subject, not a specialist one.

Today's article topic: {topic}

Produce three parts.

1. expressions: {expression_count} general-purpose expressions that native speakers use frequently across everyday, \
workplace, and academic conversation: phrasal verbs, collocations, idioms, and discourse phrases. \
Target CEFR B2 to C1+: common enough that a native speaker uses them weekly, yet ones a B2 learner \
would not produce on their own. Avoid topic-specific jargon, dated idioms, and slang that ages fast. \
The expressions need not relate to the article topic. Mix registers (casual, workplace, discussion). \
For each give the phrase, a plain-English meaning, a usage note of at most 20 words (register and the \
one thing learners get wrong; no full sentences needed), and 2 example sentences that sound like real speech.

2. article: a short article of 250 to 350 words on the topic, written for a smart general reader. \
If web search tools are available, run at most 3 searches to ground the article in accurate, current \
facts (dates, names, figures) and prefer a recent development or debate as the angle; never invent \
specifics you did not verify. In sources, list only the web pages you actually drew on (page title \
and exact URL from the search results); leave it empty if you used none. \
Use 3 to 5 paragraphs separated by blank lines. Take a clear angle so there is something to discuss. \
Then write 3 discussion questions that check the main claim, a supporting detail, and an implication. \
Each question is one short sentence of at most 14 words, in plain conversational wording a friend \
would ask across a table. No compound questions, no "explain the writer's reasoning", no quoting. \
Example of the right length: "Why does the writer call the space race a bad label?" \
Questions should invite explanation, not yes/no. \
For each question give evidence: 1 or 2 passages copied word for word from the article body (exact \
substrings, 5 to 30 words each, same capitalization and punctuation) that the answer rests on.

3. vocabulary: {vocabulary_count} words at B2 to C1+ level connected to the topic. Draw from the \
article body where it offers strong candidates, and fill the rest with words a well-read speaker would \
use when discussing this subject even if they do not appear in the article. Prefer words useful across \
academic and professional English over topic-specific jargon; no proper nouns. \
For each give the word, part of speech, a concise learner-dictionary definition, and one example \
sentence different from the article.

Set topic to the article topic. Use American English. Return only the structured output."""


EXCLUSIONS_TEMPLATE = """

Already covered in earlier sessions. Do not reuse any of these.
Expressions: {expressions}
Words: {words}"""

SKILLS_PREAMBLE = """Before writing, invoke each of these skills with the Skill tool and follow \
their instructions while producing the content: {skills}.

"""


FIRECRAWL_MCP: dict = {
    "mcpServers": {"firecrawl": {"type": "http", "url": "https://mcp.firecrawl.dev/v2/mcp-oauth"}}
}
BUILTIN_TOOLS = ("Skill", "Read")
WEB_TOOLS = ("mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_scrape")


class ClaudeCliGenerator:
    def __init__(
        self,
        model: str = "opus",
        effort: str = "xhigh",
        skills: tuple[str, ...] = (),
        mcp_config: dict = FIRECRAWL_MCP,
        timeout_s: float = 300,
    ) -> None:
        self._model = model
        self._effort = effort
        self._skills = skills
        self._mcp_config = mcp_config
        self._timeout_s = timeout_s

    def build_prompt(self, topic: str, exclude: Exclusions | None = None) -> str:
        prompt = PROMPT_TEMPLATE.format(
            topic=topic, expression_count=EXPRESSION_COUNT, vocabulary_count=VOCABULARY_COUNT
        )
        if self._skills:
            prompt = SKILLS_PREAMBLE.format(skills=", ".join(self._skills)) + prompt
        if exclude:
            prompt += EXCLUSIONS_TEMPLATE.format(
                expressions="; ".join(exclude.expressions) or "none",
                words=", ".join(exclude.words) or "none",
            )
        return prompt

    def build_command(self) -> list[str]:
        return [
            "claude",
            "-p",
            "--model",
            self._model,
            "--effort",
            self._effort,
            "--output-format",
            "stream-json",
            "--verbose",
            "--json-schema",
            json.dumps(SESSION_SCHEMA),
            "--tools",
            ",".join(BUILTIN_TOOLS),
            "--allowedTools",
            ",".join(BUILTIN_TOOLS + WEB_TOOLS),
            "--setting-sources",
            "user",
            "--strict-mcp-config",
            "--mcp-config",
            json.dumps(self._mcp_config),
            "--no-session-persistence",
        ]

    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> SessionContent:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        tracker = StreamTracker(on_progress or (lambda _: None))
        try:
            proc = subprocess.Popen(
                self.build_command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except FileNotFoundError as e:
            raise GenerationError("claude CLI not found on PATH") from e
        assert proc.stdin and proc.stdout and proc.stderr
        proc.stdin.write(self.build_prompt(topic, exclude))
        proc.stdin.close()
        killer = threading.Timer(self._timeout_s, proc.kill)
        killer.start()
        result: dict | None = None
        try:
            for line in proc.stdout:
                event = self._parse_event(line)
                if event is None:
                    continue
                if event.get("type") == "result":
                    result = event
                tracker.feed(event)
            stderr = proc.stderr.read()
            proc.wait()
        finally:
            timed_out = not killer.is_alive()
            killer.cancel()
        if timed_out:
            raise GenerationError(f"claude timed out after {self._timeout_s:.0f}s")
        if proc.returncode != 0:
            raise GenerationError(f"claude exited {proc.returncode}: {stderr.strip()[-500:]}")
        if result is None:
            raise GenerationError("claude produced no result event")
        return self.parse_result(result)

    @staticmethod
    def _parse_event(line: str) -> dict | None:
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def parse_result(envelope: dict) -> SessionContent:
        if envelope.get("is_error"):
            raise GenerationError(str(envelope.get("result", "unknown error")))
        payload = envelope.get("structured_output")
        if payload is None:
            raise GenerationError("claude returned no structured output")
        try:
            return SessionContent.model_validate(payload)
        except ValidationError as e:
            raise GenerationError(f"structured output failed validation: {e}") from e
