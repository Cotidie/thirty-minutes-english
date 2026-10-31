from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from claude_agent_sdk import create_sdk_mcp_server, tool
from pydantic import ValidationError

from app.generation.exclusions import Exclusions
from app.generation.progress import Progress, StreamTracker
from app.llm import WEB_TOOLS, Claude, GenerationError, McpServer, firecrawl
from app.models import Draft
from app.pictures.scenes import CAPTION_RULES, SCENE_RULES

OnProgress = Callable[[Progress], None]

class Generator(Protocol):
    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> Draft: ...


VOCABULARY_COUNT = 10

SESSION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic", "article", "vocabulary"],
    "properties": {
        "topic": {"type": "string"},
        "article": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "body", "questions", "sources", "translation", "figures", "picture", "paragraph_picture"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "figures": {
                    "type": "array",
                    "maxItems": 2,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["after", "image_url", "page_url", "credit", "caption"],
                        "properties": {
                            "after": {"type": "integer", "minimum": 0},
                            "image_url": {"type": "string"},
                            "page_url": {"type": "string"},
                            "credit": {"type": "string"},
                            "caption": {"type": "string"},
                        },
                    },
                },
                "picture": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["scene", "caption"],
                    "properties": {"scene": {"type": "string"}, "caption": {"type": "string"}},
                },
                "paragraph_picture": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["after", "scene", "caption"],
                    "properties": {"after": {"type": "integer", "minimum": 1}, "scene": {"type": "string"}, "caption": {"type": "string"}},
                },
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
                "required": ["word", "pos", "definition", "synonyms", "example", "korean", "scene", "caption"],
                "properties": {
                    "word": {"type": "string"},
                    "pos": {"type": "string"},
                    "definition": {"type": "string"},
                    "synonyms": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}},
                    "example": {"type": "string"},
                    "korean": {"type": "string"},
                    "scene": {"type": "string"},
                    "caption": {"type": "string"},
                },
            },
        },
    },
}

PROMPT_TEMPLATE = """You are preparing material for a 30-minute English conversation practice session \
between two Korean graduate students at roughly B2 level who want to sound natural. Topics rotate across \
computer science, industrial engineering, economics, AI, literature, world history, world affairs, Korean society, and research life; \
treat each as a general-interest subject, not a specialist one.

Today's article topic: {topic}

Produce two parts.

1. article: a short article of 250 to 350 words on the topic, written for a smart general reader. \
Run at most 3 web searches, with firecrawl_search first and WebSearch only when firecrawl_search \
fails or finds nothing usable, to ground the article in accurate, current facts (dates, names, figures) and prefer a recent development or debate as the angle; never invent \
specifics you did not verify. In sources, list only the web pages you actually drew on (page title \
and exact URL from the search results); leave it empty if you used none. \
Use 3 to 5 paragraphs separated by blank lines. Take a clear angle so there is something to discuss. \
Then run the {article_skill} skill on the title and body in its embedded mode: strip the AI patterns it lists, \
keep every fact, name, number, and date, keep 3 to 5 paragraphs separated by blank lines, and keep only the \
final text. The evidence and the translation below are copied from this final body. \
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
with its neighbors in mind so the Korean reads well in sequence; keep names, figures, and dates as they are. \
Then give figures: 2 images you saw on the pages you drew on (firecrawl_scrape with the images format \
lists a page's images): a photo of the place, people, or thing, a diagram, or a map. Never a logo, ad, icon, \
author photo, or tracking pixel. Look through every page you drew on before giving fewer than 2. The first is the cover, shown under the title: the image that best shows what \
the whole article is about (often the lead photo of the main source); give it after 0. The second shows what \
one paragraph says; give it after (the paragraph it belongs under, counted from 1). When only one image fits, \
make it the cover. For each give after, image_url (the exact image address from the page), page_url (the page \
it was on), credit (the outlet or photographer the page names), and caption (one plain sentence on what it \
shows and why it matters to the article or to that paragraph). Leave figures empty when no such image turned \
up. Always give picture too: one moment that captures the whole article and that a photo could capture, in two \
or three concrete sentences (the place, who is there, what they are doing, details a viewer could point at; no \
text or signs), and a one-sentence caption. It is drawn as the cover when no cover image can be used. \
Always give paragraph_picture as well: a different moment, from one paragraph, written the same way, with after \
(the paragraph it belongs under, counted from 1) and a one-sentence caption. It is drawn under that paragraph when \
no image lands under a paragraph, so that the article always shows exactly 2 images.

2. vocabulary: {vocabulary_count} words at B2 to C1+ level connected to the topic. Draw from the \
article body where it offers strong candidates, and fill the rest with words a well-read speaker would \
use when discussing this subject even if they do not appear in the article. Prefer words useful across \
academic and professional English over topic-specific jargon; no proper nouns. \
For each give the word, part of speech, a concise learner-dictionary definition, synonyms (1 or 2 more common words \
that could replace it in this sense), one example \
sentence different from the article, korean (the Korean equivalent in the sense used here, one or two \
words, no explanation), a scene: {scene_rules}, and a caption for the scene: {caption_rules}. Vary the scenes across the words: \
different places, times of day, and kinds of people, so no two look alike.

Set topic to the article topic. Use American English. Return only the structured output."""


CHECK_ITEMS_RULE = """

Earlier sessions already taught some words. Before you finalize, call check_items with every \
vocabulary word you chose. Replace each one it reports as already taught with a fresh word, then call \
it again with the replacements until it reports nothing."""

SKILLS_PREAMBLE = """Before writing, invoke the {skill} skill with the Skill tool and follow its \
instructions while producing every part of the content.

"""


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
APP_SKILL = "english-session:session-writing"
# Vendored from github.com/blader/humanizer (MIT, v3.1.0); the article alone goes through it.
ARTICLE_SKILL = "english-session:humanizer"


# The cutoff for a hung run, not a budget: Opus at xhigh takes about 300s on its own.
TIMEOUT_S = 600


class ClaudeGenerator:
    """Runs on the app's own skills only (backend/plugin), so a session reads the same on any machine."""

    def __init__(
        self,
        model: str = "opus",
        effort: str | None = "xhigh",
        firecrawl_key: str = "",
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self.claude = Claude(
            model,
            effort,
            timeout_s,
            tools=("Read", *WEB_TOOLS),
            mcp=(firecrawl(firecrawl_key),),
            skills=(APP_SKILL, ARTICLE_SKILL),
            plugins=(str(PLUGIN_DIR),),
            partial=True,
        )

    def build_prompt(self, topic: str, exclude: Exclusions | None = None) -> str:
        prompt = PROMPT_TEMPLATE.format(
            topic=topic,
            vocabulary_count=VOCABULARY_COUNT,
            article_skill=ARTICLE_SKILL,
            scene_rules=SCENE_RULES,
            caption_rules=CAPTION_RULES,
        )
        prompt = SKILLS_PREAMBLE.format(skill=APP_SKILL) + prompt
        if exclude:
            prompt += CHECK_ITEMS_RULE
        return prompt

    def generate(
        self,
        topic: str,
        on_progress: OnProgress | None = None,
        exclude: Exclusions | None = None,
    ) -> Draft:
        tracker = StreamTracker(on_progress or (lambda _: None))
        extra = (check_items_server(exclude),) if exclude else ()
        payload = self.claude.run(self.build_prompt(topic, exclude), SESSION_SCHEMA, tracker.feed, extra)
        try:
            return Draft.model_validate(payload)
        except ValidationError as e:
            raise GenerationError(f"structured output failed validation: {e}") from e
