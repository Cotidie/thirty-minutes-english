"""Review records for live rounds. GPT-Live has no structured output, so a
round leaves two transcripts behind; a text model turns a batch of them into
records once, when the user opens the summary. Each agent folder carries the
prompt and schema for its own kind of round."""

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

from app.models import Ask, Correction, PhraseCard, Reading
from app.store import SessionStore

log = logging.getLogger(__name__)

RESPONSES_URL = "https://api.openai.com/v1/responses"


class Extractor(Protocol):
    """Turns rounds into records, keyed by round id."""

    def extract(self, rounds: list) -> dict[int, object]: ...


class OpenAIExtractor:
    """One call for the whole batch. The model answers per round id."""

    def __init__(self, api_key: str, agent_dir: Path, model: str, schema_name: str, url: str = RESPONSES_URL):
        self.api_key = api_key
        self.prompt = (agent_dir / "prompts" / "summarize.md").read_text()
        self.schema = json.loads((agent_dir / schema_name).read_text())
        self.model = model
        self.url = url

    def respond(self, rows: list[dict]) -> dict:
        body = json.dumps(
            {
                "model": self.model,
                "reasoning": {"effort": "low"},
                "input": [
                    {"role": "developer", "content": self.prompt},
                    {"role": "user", "content": json.dumps(rows, ensure_ascii=False)},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": self.schema.get("title", "Records"),
                        "schema": self.schema,
                        "strict": True,
                    }
                },
            }
        ).encode()
        req = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            payload = json.load(res)
        return json.loads(_output_text(payload))


class PhraseCardExtractor(OpenAIExtractor):
    """Asks to cards: one expression, its alternatives, and when it fits."""

    def __init__(self, api_key: str, agent_dir: Path, model: str, url: str = RESPONSES_URL):
        super().__init__(api_key, agent_dir, model, "cards.schema.json", url)

    def extract(self, rounds: list[Ask]) -> dict[int, PhraseCard]:
        rows = [{"id": a.id, "user": a.user_text, "coach": a.coach_text} for a in sorted(rounds, key=lambda a: a.id)]
        answer = self.respond(rows)
        return {card["id"]: PhraseCard.model_validate(card) for card in answer["cards"]}


class CorrectionExtractor(OpenAIExtractor):
    """Readings to the list of words the coach stopped on."""

    def __init__(self, api_key: str, agent_dir: Path, model: str, url: str = RESPONSES_URL):
        super().__init__(api_key, agent_dir, model, "feedback.schema.json", url)

    def extract(self, rounds: list[Reading]) -> dict[int, list[Correction]]:
        rows = [
            {"id": r.id, "paragraph": r.paragraph, "reader": r.user_text, "coach": r.coach_text}
            for r in sorted(rounds, key=lambda r: r.id)
        ]
        answer = self.respond(rows)
        return {
            entry["id"]: [Correction.model_validate(c) for c in entry["corrections"]]
            for entry in answer["readings"]
        }


def _output_text(payload: dict) -> str:
    """The first output_text part of a Responses answer."""
    for item in payload.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                return part.get("text", "")
    return payload.get("output_text", "")


class Review:
    """Rounds with their records, extracting the ones that do not have any yet."""

    def __init__(self, store: SessionStore, extractor: Extractor | None):
        self.store = store
        self.extractor = extractor

    def _fill(self, rounds: list, missing: list, keep) -> list:
        if not missing or self.extractor is None:
            return rounds
        try:
            extracted = self.extractor.extract(missing)
        except (urllib.error.URLError, ValueError, KeyError) as e:
            log.warning("extraction failed, returning transcripts: %s", e)
            return rounds
        for round_ in missing:
            record = extracted.get(round_.id)
            if record is not None:
                keep(round_, record)
        return rounds


class AskReview(Review):
    def cards_for(self, session_id: int | None = None) -> list[Ask]:
        asks = self.store.list_asks(session_id)

        def keep(ask: Ask, card: PhraseCard) -> None:
            self.store.set_ask_card(ask.id, card)
            ask.card = card

        return self._fill(asks, [a for a in asks if a.card is None], keep)


class ReadingReview(Review):
    def corrections_for(self, session_id: int | None = None) -> list[Reading]:
        readings = self.store.list_readings(session_id)

        def keep(reading: Reading, corrections: list[Correction]) -> None:
            self.store.set_reading_corrections(reading.id, corrections)
            reading.corrections = corrections

        return self._fill(readings, [r for r in readings if r.corrections is None], keep)
