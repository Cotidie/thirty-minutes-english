"""A sentence the reader made with a target, said back the native way with a line per change.

GPT-Live only hears the sentence and reads the answer aloud; the judgment is a
text run of the claude CLI with the prompt in the example-coach folder.
"""

from pathlib import Path
from typing import Literal, Protocol

from app.claude_cli import ClaudeCli, structured_output
from app.models import ExampleFeedback

Kind = Literal["expression", "word"]
TEMPLATES: dict[Kind, str] = {"expression": "feedback.md", "word": "feedback-word.md"}

FEEDBACK_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["paraphrase", "feedback"],
    "properties": {
        "paraphrase": {"type": "string"},
        "feedback": {"type": "array", "items": {"type": "string"}},
    },
}


class Runner(Protocol):
    def run(self, prompt: str, schema: dict, on_event=None) -> dict: ...


class ExampleCoach:
    """An expression gets the light native fix (`feedback.md`); a word gets a freer
    rewording that uses it well, describing the word's picture (`feedback-word.md`)."""

    def __init__(self, cli: Runner, agent_dir: Path) -> None:
        self._cli = cli
        self._templates = {kind: (agent_dir / "prompts" / name).read_text() for kind, name in TEMPLATES.items()}

    @classmethod
    def with_cli(cls, agent_dir: Path, model: str, effort: str = "low") -> "ExampleCoach":
        return cls(ClaudeCli(model=model, effort=effort, tools=(), mcp=None, timeout_s=90), agent_dir)

    def build_prompt(
        self, expression: str, meaning: str, usage_note: str, sentence: str, kind: Kind = "expression", scene: str = ""
    ) -> str:
        """For a word, `usage_note` is "part of speech: noun" and `scene` what its picture shows."""
        values = {
            "expression": expression,
            "word": expression,
            "meaning": meaning,
            "usage_note": usage_note or "none",
            "pos": usage_note.removeprefix("part of speech:").strip() or "word",
            "scene": scene or "no picture; go by the sentence",
            "sentence": sentence,
        }
        prompt = self._templates[kind]
        for name, value in values.items():
            prompt = prompt.replace("{{" + name + "}}", value)
        return prompt

    def feedback(
        self, expression: str, meaning: str, usage_note: str, sentence: str, kind: Kind = "expression", scene: str = ""
    ) -> ExampleFeedback:
        """Raises GenerationError when the run fails."""
        prompt = self.build_prompt(expression, meaning, usage_note, sentence, kind, scene)
        return ExampleFeedback.model_validate(structured_output(self._cli.run(prompt, FEEDBACK_SCHEMA)))
