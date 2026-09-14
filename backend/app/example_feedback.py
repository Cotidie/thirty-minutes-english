"""A sentence the reader made with a target, said back the native way with a line per change.

GPT-Live only hears the sentence and reads the answer aloud; the judgment is a
text run of the claude CLI with the prompt in the example-coach folder.
"""

from pathlib import Path
from typing import Protocol

from app.claude_cli import ClaudeCli, structured_output
from app.models import ExampleFeedback

FEEDBACK_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["paraphrase", "feedback"],
    "properties": {"paraphrase": {"type": "string"}, "feedback": {"type": "string"}},
}


class Runner(Protocol):
    def run(self, prompt: str, schema: dict, on_event=None) -> dict: ...


class ExampleCoach:
    def __init__(self, cli: Runner, agent_dir: Path) -> None:
        self._cli = cli
        self._template = (agent_dir / "prompts" / "feedback.md").read_text()

    @classmethod
    def with_cli(cls, agent_dir: Path, model: str, effort: str = "low") -> "ExampleCoach":
        return cls(ClaudeCli(model=model, effort=effort, tools=(), mcp_config=None, timeout_s=90), agent_dir)

    def build_prompt(self, expression: str, meaning: str, usage_note: str, sentence: str) -> str:
        values = {"expression": expression, "meaning": meaning, "usage_note": usage_note or "none", "sentence": sentence}
        prompt = self._template
        for name, value in values.items():
            prompt = prompt.replace("{{" + name + "}}", value)
        return prompt

    def feedback(self, expression: str, meaning: str, usage_note: str, sentence: str) -> ExampleFeedback:
        """Raises GenerationError when the run fails."""
        envelope = self._cli.run(self.build_prompt(expression, meaning, usage_note, sentence), FEEDBACK_SCHEMA)
        return ExampleFeedback.model_validate(structured_output(envelope))
