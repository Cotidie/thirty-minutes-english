"""Review cards for Ask rounds. GPT-Live has no structured output, so a round
leaves two transcripts behind; a text model turns the ones without a card into
cards once, when the user opens the summary. The phrase-coach folder carries
the prompt and schema."""

import json
import logging
from pathlib import Path
from typing import Protocol

from openai import OpenAI, OpenAIError

from app.db.records import RecordRepo
from app.models import Ask, PhraseCard

log = logging.getLogger(__name__)

SCHEMA_FILE = "cards.schema.json"


class Extractor(Protocol):
    def extract(self, asks: list[Ask]) -> dict[int, PhraseCard]: ...


class PhraseCardExtractor:
    """One OpenAI Responses call for the whole batch; the model answers per ask id."""

    def __init__(self, api_key: str, agent_dir: Path, model: str, client: OpenAI | None = None):
        self.prompt = (agent_dir / "prompts" / "summarize.md").read_text()
        self.schema = json.loads((agent_dir / SCHEMA_FILE).read_text())
        self.model = model
        self._client = client or OpenAI(api_key=api_key, timeout=60)

    def extract(self, asks: list[Ask]) -> dict[int, PhraseCard]:
        rows = [{"id": a.id, "user": a.user_text, "coach": a.coach_text} for a in sorted(asks, key=lambda a: a.id)]
        response = self._client.responses.create(
            model=self.model,
            reasoning={"effort": "low"},
            input=[
                {"role": "developer", "content": self.prompt},
                {"role": "user", "content": json.dumps(rows, ensure_ascii=False)},
            ],
            text={"format": {"type": "json_schema", "name": self.schema.get("title", "Records"), "schema": self.schema, "strict": True}},
        )
        answer = json.loads(response.output_text)
        return {card["id"]: PhraseCard.model_validate(card) for card in answer["cards"]}


def cards_for(records: RecordRepo, extractor: Extractor | None, session_id: int | None = None) -> list[Ask]:
    """The asks with their cards, extracting and keeping the missing ones. A failed
    extraction still returns the transcripts."""
    asks = records.list_asks(session_id)
    missing = [a for a in asks if a.card is None]
    if not missing or extractor is None:
        return asks
    try:
        cards = extractor.extract(missing)
    except (OpenAIError, ValueError, KeyError) as e:
        log.warning("card extraction failed, returning transcripts: %s", e)
        return asks
    for ask in missing:
        if (card := cards.get(ask.id)) is not None:
            records.set_ask_card(ask.id, card)
            ask.card = card
    return asks
