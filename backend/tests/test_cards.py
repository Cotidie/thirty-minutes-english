import json

import pytest
from fastapi.testclient import TestClient

from app.coaching.cards import PhraseCardExtractor, cards_for
from app.db import Database
from app.main import create_app
from app.models import PhraseCard
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor


class FakeExtractor:
    def __init__(self, error: Exception | None = None):
        self.batches: list[list[int]] = []
        self.error = error

    def extract(self, asks):
        self.batches.append([a.id for a in asks])
        if self.error:
            raise self.error
        return {
            a.id: PhraseCard(asked=a.user_text, english=a.coach_text, alternatives=[], note="note")
            for a in asks
        }


@pytest.fixture
def store(tmp_path) -> Database:
    return Database(tmp_path / "s.db")


def test_extracts_only_the_asks_without_a_card(store):
    first = store.records.add_ask(None, "눈치 좀 챙겨", "Read the room.", 11)
    store.records.set_ask_card(first.id, PhraseCard(asked="눈치 좀 챙겨", english="Read the room.", note="kept"))
    second = store.records.add_ask(None, "I have much work", "I'm swamped.", 9)
    extractor = FakeExtractor()

    cards = cards_for(store.records, extractor)

    assert extractor.batches == [[second.id]]
    assert {a.id: a.card.note for a in cards} == {first.id: "kept", second.id: "note"}


def test_a_second_review_calls_nothing(store):
    store.records.add_ask(None, "q", "a", 1)
    extractor = FakeExtractor()
    cards_for(store.records, extractor)
    cards_for(store.records, extractor)

    assert len(extractor.batches) == 1


def test_a_failed_extraction_still_returns_the_transcripts(store):
    store.records.add_ask(None, "q", "a", 1)
    cards = cards_for(store.records, FakeExtractor(ValueError("bad json")))
    assert [a.coach_text for a in cards] == ["a"]
    assert cards[0].card is None


def test_review_without_an_extractor_returns_transcripts(store):
    store.records.add_ask(None, "q", "a", 1)
    assert cards_for(store.records, None)[0].card is None


def test_cards_endpoint_narrows_to_one_session(tmp_path):
    extractor = FakeExtractor()
    store = Database(tmp_path / "s.db")
    app = create_app(store, Services(FakeGenerator(), extractor=extractor), InlineExecutor())
    with TestClient(app) as c:
        session_id = c.post("/api/sessions", json={"topic": "Digital twins"}).json()["session_id"]
        c.post("/api/asks", json={"session_id": session_id, "user_text": "mine", "coach_text": "a"})
        c.post("/api/asks", json={"user_text": "loose", "coach_text": "b"})

        scoped = c.post("/api/asks/cards", params={"session_id": session_id}).json()
        assert [a["user_text"] for a in scoped] == ["mine"]
        assert scoped[0]["card"]["english"] == "a"

        assert len(c.post("/api/asks/cards").json()) == 2


def test_extractor_sends_rounds_and_reads_the_answer(tmp_path, http):
    agent_dir = tmp_path / "phrase"
    (agent_dir / "prompts").mkdir(parents=True)
    (agent_dir / "prompts" / "summarize.md").write_text("Turn rounds into cards.")
    (agent_dir / "cards.schema.json").write_text(json.dumps({"title": "PhraseCards", "type": "object"}))
    extractor = PhraseCardExtractor("sk-test", agent_dir, "gpt-5.6-luna")

    card = {"id": 7, "asked": "눈치", "english": "Read the room.", "alternatives": [], "note": "n"}
    http.json = {"output": [{"content": [{"type": "output_text", "text": json.dumps({"cards": [card]})}]}]}

    store = Database(tmp_path / "s.db")
    ask = store.records.add_ask(None, "눈치 좀 챙겨", "Read the room.", 11)
    object.__setattr__(ask, "id", 7)

    cards = extractor.extract([ask])

    assert http.requests[0].headers["Authorization"] == "Bearer sk-test"
    assert http.sent()["model"] == "gpt-5.6-luna"
    assert json.loads(http.sent()["input"][1]["content"]) == [
        {"id": 7, "user": "눈치 좀 챙겨", "coach": "Read the room."}
    ]
    assert cards[7].english == "Read the room."

