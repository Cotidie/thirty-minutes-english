"""A sentence the reader made with one of the session's words, said back the way a native speaker
would describe the word's picture, with a line per change.

GPT-Live only hears the sentence and reads the answer aloud; the judgment is a
text run of the claude CLI with the prompt in the example-coach folder.
"""

from pathlib import Path

from app.llm import Claude, Runner
from app.models import ExampleFeedback
from app.templates import fill

PROMPT = "feedback.md"

FEEDBACK_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["paraphrase", "feedback"],
    "properties": {
        "paraphrase": {"type": "string"},
        "feedback": {"type": "array", "items": {"type": "string"}},
    },
}


class ExampleCoach:
    """A free rewording that uses the word well and describes its picture (`prompts/feedback.md`)."""

    def __init__(self, cli: Runner, agent_dir: Path) -> None:
        self._cli = cli
        self._template = (agent_dir / "prompts" / PROMPT).read_text()

    @classmethod
    def with_cli(cls, agent_dir: Path, model: str, effort: str | None = "low") -> "ExampleCoach":
        return cls(Claude(model, effort), agent_dir)

    def build_prompt(self, word: str, pos: str, meaning: str, sentence: str, scene: str = "") -> str:
        """`scene` is what the word's picture shows."""
        return fill(self._template, word=word, pos=pos, meaning=meaning, scene=scene or "no picture; go by the sentence", sentence=sentence)

    def feedback(self, word: str, pos: str, meaning: str, sentence: str, scene: str = "") -> ExampleFeedback:
        """Raises GenerationError when the run fails."""
        return ExampleFeedback.model_validate(self._cli.run(self.build_prompt(word, pos, meaning, sentence, scene), FEEDBACK_SCHEMA))
