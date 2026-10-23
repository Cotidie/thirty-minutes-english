"""A paragraph the reader summed up out loud, judged against the paragraph in a fixed shape read
at a glance: the one point missed, up to two wordings bettered, and a model answer.

Gemini's transcription model writes the summary down; the judgment is a text run of the
claude CLI with the prompt and its output schema in the summary-coach folder.
"""

import json
from pathlib import Path

from app.llm import Claude, Runner
from app.models import SummaryFeedback
from app.templates import fill

TEMPLATE = "feedback.md"
SCHEMA = "feedback.schema.json"


class SummaryCoach:
    def __init__(self, cli: Runner, agent_dir: Path) -> None:
        self._cli = cli
        self._template = (agent_dir / "prompts" / TEMPLATE).read_text()
        self._schema = json.loads((agent_dir / "prompts" / SCHEMA).read_text())

    @classmethod
    def with_cli(cls, agent_dir: Path, model: str, effort: str | None = "low") -> "SummaryCoach":
        return cls(Claude(model, effort), agent_dir)

    def feedback(self, paragraph: str, said: str) -> SummaryFeedback:
        """Raises GenerationError when the run fails."""
        prompt = fill(self._template, paragraph=paragraph, summary=said)
        return SummaryFeedback.model_validate(self._cli.run(prompt, self._schema))
