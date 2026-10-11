"""A paragraph the reader summed up out loud, judged against the paragraph: what they missed,
what was unskilled in their wording, and their summary with those fixes put in.

The live model only listens and transcribes; the judgment is a text run of the claude CLI
with the prompt in the summary-coach folder.
"""

from pathlib import Path

from app.llm import Claude, Runner
from app.models import SummaryFeedback
from app.templates import fill

TEMPLATE = "feedback.md"

FEEDBACK_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["missed", "fixes", "summary"],
    "properties": {
        "missed": {"type": "array", "maxItems": 2, "items": {"type": "string"}},
        "summary": {"type": "string"},
        "fixes": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["said", "better", "why"],
                "properties": {"said": {"type": "string"}, "better": {"type": "string"}, "why": {"type": "string"}},
            },
        },
    },
}


class SummaryCoach:
    def __init__(self, cli: Runner, agent_dir: Path) -> None:
        self._cli = cli
        self._template = (agent_dir / "prompts" / TEMPLATE).read_text()

    @classmethod
    def with_cli(cls, agent_dir: Path, model: str, effort: str | None = "low") -> "SummaryCoach":
        return cls(Claude(model, effort), agent_dir)

    def feedback(self, paragraph: str, said: str) -> SummaryFeedback:
        """Raises GenerationError when the run fails."""
        prompt = fill(self._template, paragraph=paragraph, summary=said)
        return SummaryFeedback.model_validate(self._cli.run(prompt, FEEDBACK_SCHEMA))
