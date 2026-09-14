"""Review cards for asks. GPT-Live has no structured output, so a round leaves
two transcripts behind; a text model turns a batch of them into cards once, when
the user opens the review. The prompt and schema live in the agent folder."""

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

from app.models import Ask, PhraseCard
from app.store import SessionStore

log = logging.getLogger(__name__)

RESPONSES_URL = "https://api.openai.com/v1/responses"


class CardExtractor(Protocol):
    def extract(self, asks: list[Ask]) -> dict[int, PhraseCard]: ...


class OpenAICardExtractor:
    """One call for the whole batch. The model is told to answer per ask id."""

    def __init__(self, api_key: str, agent_dir: Path, model: str, url: str = RESPONSES_URL):
        self.api_key = api_key
        self.prompt = (agent_dir / "prompts" / "summarize.md").read_text()
        self.schema = json.loads((agent_dir / "cards.schema.json").read_text())
        self.model = model
        self.url = url

    def extract(self, asks: list[Ask]) -> dict[int, PhraseCard]:
        rounds = [
            {"id": a.id, "user": a.user_text, "coach": a.coach_text}
            for a in sorted(asks, key=lambda a: a.id)
        ]
        body = json.dumps(
            {
                "model": self.model,
                "reasoning": {"effort": "low"},
                "input": [
                    {"role": "developer", "content": self.prompt},
                    {"role": "user", "content": json.dumps(rounds, ensure_ascii=False)},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "PhraseCards",
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
        return _cards_by_id(_output_text(payload))


def _output_text(payload: dict) -> str:
    """The first output_text part of a Responses answer."""
    for item in payload.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                return part.get("text", "")
    return payload.get("output_text", "")


def _cards_by_id(raw: str) -> dict[int, PhraseCard]:
    cards = json.loads(raw)["cards"]
    return {card["id"]: PhraseCard.model_validate(card) for card in cards}


class AskReview:
    """Asks with their cards, extracting the ones that do not have one yet."""

    def __init__(self, store: SessionStore, extractor: CardExtractor | None):
        self.store = store
        self.extractor = extractor

    def cards_for(self, session_id: int | None = None) -> list[Ask]:
        asks = self.store.list_asks(session_id)
        missing = [a for a in asks if a.card is None]
        if not missing or self.extractor is None:
            return asks
        try:
            extracted = self.extractor.extract(missing)
        except (urllib.error.URLError, ValueError, KeyError) as e:
            log.warning("card extraction failed, returning transcripts: %s", e)
            return asks
        for ask in missing:
            card = extracted.get(ask.id)
            if card is not None:
                self.store.set_ask_card(ask.id, card)
                ask.card = card
        return asks
