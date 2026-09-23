from collections.abc import Callable
from typing import Protocol

from claude_agent_sdk import create_sdk_mcp_server, tool
from pydantic import ValidationError

from app.generation.exclusions import Exclusions
from app.generation.progress import Progress, StreamTracker
from app.llm import WEB_TOOLS, Claude, GenerationError, McpServer
from app.models import SessionContent
from app.pictures.scenes import SCENE_RULES

OnProgress = Callable[[Progress], None]

class Generator(Protocol):
    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> SessionContent: ...


EXPRESSION_COUNT = 5
VOCABULARY_COUNT = 10

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
                "required": ["phrase", "meaning", "usage_note", "examples", "korean"],
                "properties": {
                    "phrase": {"type": "string"},
                    "meaning": {"type": "string"},
                    "usage_note": {"type": "string"},
                    "examples": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}},
                    "korean": {"type": "string"},
                },
            },
        },
        "article": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "body", "questions", "sources", "translation"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "translation": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["en", "ko"],
                        "properties": {"en": {"type": "string"}, "ko": {"type": "string"}},
                    },
                },
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
                            "evidence": {"type": "array", "minItems": 0, "maxItems": 2, "items": {"type": "string"}},
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
                "required": ["word", "pos", "definition", "example", "korean", "scene"],
                "properties": {
                    "word": {"type": "string"},
                    "pos": {"type": "string"},
                    "definition": {"type": "string"},
                    "example": {"type": "string"},
                    "korean": {"type": "string"},
                    "scene": {"type": "string"},
                },
            },
        },
    },
}

PROMPT_TEMPLATE = """You are preparing material for a 30-minute English conversation practice session \
between two Korean graduate students at roughly B2 level who want to sound natural. Topics rotate across \
computer science, industrial engineering, AI, literature, world history, world affairs, Korean society, and research life; \
treat each as a general-interest subject, not a specialist one.

Today's article topic: {topic}

Produce three parts.

1. expressions: {expression_count} general-purpose expressions that native speakers use frequently across everyday, \
workplace, and academic conversation: phrasal verbs, collocations, idioms, and discourse phrases. \
Target CEFR B2 to C1+: common enough that a native speaker uses them weekly, yet ones a B2 learner \
would not produce on their own. Avoid topic-specific jargon, dated idioms, and slang that ages fast. \
The expressions need not relate to the article topic. Mix registers (casual, workplace, discussion). \
For each give the phrase, a plain-English meaning, a usage note of at most 20 words (register and the \
one thing learners get wrong; no full sentences needed), 2 example sentences that sound like real speech, \
and korean: the natural Korean equivalent of the expression, a short phrase, no explanation.

2. article: a short article of 250 to 350 words on the topic, written for a smart general reader. \
Run at most 3 web searches to ground the article in accurate, current facts (dates, names, figures) and prefer a recent development or debate as the angle; never invent \
specifics you did not verify. In sources, list only the web pages you actually drew on (page title \
and exact URL from the search results); leave it empty if you used none. \
Use 3 to 5 paragraphs separated by blank lines. Take a clear angle so there is something to discuss. \
Then write 3 discussion questions. Each is one short sentence of at most 14 words, in plain \
conversational wording a friend would ask across a table. No compound questions, no "explain the \
writer's reasoning", no quoting. Questions invite explanation, not yes/no. \
Example of the right length: "Why does the writer call the space race a bad label?" \
The first two are answered by the article: one on the main claim, one on a supporting detail. \
For each of those two give evidence: 1 or 2 passages copied word for word from the article body \
(exact substrings, 5 to 30 words each, same capitalization and punctuation) that the answer rests on. \
The third is an open question the article does not settle. It asks the two speakers what they think, \
about something two reasonable people would disagree on, and it grows out of the article's angle \
rather than asking about life in general. Its evidence is an empty list. \
Then give translation: every sentence of the article body, in reading order, as pairs. en is the sentence \
copied character for character from the body, final punctuation included, one sentence per pair; never \
merge or split sentences. ko is that sentence in natural written Korean (해라체, "~다"로 끝맺기), translated \
with its neighbors in mind so the Korean reads well in sequence; keep names, figures, and dates as they are.

3. vocabulary: {vocabulary_count} words at B2 to C1+ level connected to the topic. Draw from the \
article body where it offers strong candidates, and fill the rest with words a well-read speaker would \
use when discussing this subject even if they do not appear in the article. Prefer words useful across \
academic and professional English over topic-specific jargon; no proper nouns. \
For each give the word, part of speech, a concise learner-dictionary definition, one example \
sentence different from the article, korean (the Korean equivalent in the sense used here, one or two \
words, no explanation), and a scene: {scene_rules}. Vary the scenes across the words: \
different places, times of day, and kinds of people, so no two look alike.

Set topic to the article topic. Use American English. Return only the structured output."""


CHECK_ITEMS_RULE = """

Earlier sessions already taught some expressions and words. Before you finalize, call check_items with \
every expression phrase and every vocabulary word you chose. Replace each one it reports as already \
taught with a fresh item, then call it again with the replacements until it reports nothing."""

SKILLS_PREAMBLE = """Before writing, invoke each of these skills with the Skill tool and follow \
their instructions while producing the content: {skills}.

"""


def check_items_reply(exclude: Exclusions, args: dict) -> str:
    taught = exclude.taught(args.get("expressions", []), args.get("words", []))
    return f"Already taught, replace: {'; '.join(taught)}" if taught else "None of these were taught before."


def check_items_server(exclude: Exclusions) -> McpServer:
    """An in-process tool the model checks its picks against, so the banned list stays out of the prompt."""

    @tool("check_items", "Which of these expressions and words earlier sessions already taught", {"expressions": list[str], "words": list[str]})
    async def check_items(args: dict) -> dict:
        return {"content": [{"type": "text", "text": check_items_reply(exclude, args)}]}

    return McpServer("session", create_sdk_mcp_server("session", tools=[check_items]), ("mcp__session__check_items",))


class ClaudeGenerator:
    def __init__(self, model: str = "opus", effort: str = "xhigh", skills: tuple[str, ...] = (), timeout_s: float = 300) -> None:
        self._skills = skills
        self.claude = Claude(model, effort, timeout_s, tools=("Read", *WEB_TOOLS), skills=skills)

    def build_prompt(self, topic: str, exclude: Exclusions | None = None) -> str:
        prompt = PROMPT_TEMPLATE.format(
            topic=topic, expression_count=EXPRESSION_COUNT, vocabulary_count=VOCABULARY_COUNT, scene_rules=SCENE_RULES
        )
        if self._skills:
            prompt = SKILLS_PREAMBLE.format(skills=", ".join(self._skills)) + prompt
        if exclude:
            prompt += CHECK_ITEMS_RULE
        return prompt

    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> SessionContent:
        tracker = StreamTracker(on_progress or (lambda _: None))
        extra = (check_items_server(exclude),) if exclude else ()
        payload = self.claude.run(self.build_prompt(topic, exclude), SESSION_SCHEMA, tracker.feed, extra)
        try:
            return SessionContent.model_validate(payload)
        except ValidationError as e:
            raise GenerationError(f"structured output failed validation: {e}") from e
