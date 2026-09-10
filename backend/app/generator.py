import json
import os
import subprocess
from typing import Protocol

from pydantic import ValidationError

from app.models import SessionContent


class GenerationError(Exception):
    pass


class Generator(Protocol):
    def generate(self, topic: str) -> SessionContent: ...


SESSION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic", "expressions", "article", "vocabulary"],
    "properties": {
        "topic": {"type": "string"},
        "expressions": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
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
            "required": ["title", "body", "questions"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
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
            "minItems": 8,
            "maxItems": 8,
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
between two graduate students in AI, computer science, and industrial engineering. \
They are Korean speakers at roughly B2 level who want to sound natural.

Today's article topic: {topic}

Produce three parts.

1. expressions: 5 idioms or expressions native speakers use often in everyday and workplace conversation. \
Pick ones that are common but that a B2 learner would not produce on their own. Mix registers \
(casual, workplace, discussion). For each give the phrase, a plain-English meaning, a usage note of at most \
20 words (register and the one thing learners get wrong; no full sentences needed), and 2 example sentences \
that sound like real speech.

2. article: a short article of 250 to 350 words on the topic, written for a smart general reader. \
Use 3 to 5 paragraphs separated by blank lines. Take a clear angle so there is something to discuss. \
Then write 3 comprehension questions that check whether the reader understood the main claim, \
a supporting detail, and an implication. Questions should invite explanation, not yes/no. \
For each question give evidence: 1 or 2 passages copied word for word from the article body (exact \
substrings, 5 to 30 words each, same capitalization and punctuation) that the answer rests on.

3. vocabulary: 8 words at B2 to C1 level or above that appear verbatim in the article body. \
Prefer words useful across academic and professional English over topic-specific jargon. \
For each give the word, part of speech, a concise learner-dictionary definition, and one example \
sentence different from the article.

Set topic to the article topic. Use American English. Return only the structured output."""


class ClaudeCliGenerator:
    def __init__(self, model: str = "opus", timeout_s: float = 300) -> None:
        self._model = model
        self._timeout_s = timeout_s

    def build_prompt(self, topic: str) -> str:
        return PROMPT_TEMPLATE.format(topic=topic)

    def build_command(self) -> list[str]:
        return [
            "claude",
            "-p",
            "--model",
            self._model,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(SESSION_SCHEMA),
            "--restricted",
            "--tools",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]

    def generate(self, topic: str) -> SessionContent:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            proc = subprocess.run(
                self.build_command(),
                input=self.build_prompt(topic),
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                env=env,
            )
        except FileNotFoundError as e:
            raise GenerationError("claude CLI not found on PATH") from e
        except subprocess.TimeoutExpired as e:
            raise GenerationError(f"claude timed out after {self._timeout_s:.0f}s") from e
        if proc.returncode != 0:
            raise GenerationError(f"claude exited {proc.returncode}: {proc.stderr.strip()[-500:]}")
        return self.parse_output(proc.stdout)

    @staticmethod
    def parse_output(stdout: str) -> SessionContent:
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise GenerationError(f"claude returned non-JSON output: {stdout[:200]}") from e
        if envelope.get("is_error"):
            raise GenerationError(str(envelope.get("result", "unknown error")))
        payload = envelope.get("structured_output")
        if payload is None:
            raise GenerationError("claude returned no structured output")
        try:
            return SessionContent.model_validate(payload)
        except ValidationError as e:
            raise GenerationError(f"structured output failed validation: {e}") from e
