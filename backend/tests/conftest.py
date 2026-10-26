import json

import httpx2
import pytest

from app.db import Database
from app.generation.generator import VOCABULARY_COUNT
from app.models import ArticleDraft, Draft, PictureDraft, Question, SentencePair, Source, Topic, VocabularyDraft
from app.topics.curated import CURATED


def sample_draft(topic: str = "Digital twins", title: str = "Twins at Work") -> Draft:
    """What a generator hands over: three paragraphs and the full set of words, no expressions."""
    return Draft(
        topic=topic,
        article=ArticleDraft(
            title=title,
            body="One.\n\nTwo two.\n\nThree.",
            questions=[
                Question(text="q1", evidence=["One."]),
                Question(text="q2", evidence=["Two two."]),
                Question(text="q3"),
            ],
            sources=[Source(title="A page", url="https://example.com")],
            translation=[SentencePair(en="One.", ko="하나다.")],
            picture=PictureDraft(after=2, scene="A tram stop in the rain at dusk, two students under one umbrella.", caption="Waiting for the tram."),
        ),
        vocabulary=[
            VocabularyDraft(word=f"word{i}", pos="noun", definition=f"def {i}", example=f"ex {i}", synonyms=[f"same {i}"], korean=f"단어 {i}", scene=f"scene {i}", caption=f"caption {i}")
            for i in range(VOCABULARY_COUNT)
        ],
    )


# Distinct words, since the corpus tells phrases apart by their letters only.
# The curated topics every new file is seeded with, in seed order.
CURATED_TOPICS = [Topic(text=text, category=category) for category, texts in CURATED.items() for text in texts]

NAMES = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet")


def seed_expressions(db: Database, n: int = 5, setting: str | None = None) -> list[int]:
    """`n` corpus expressions ("alpha phrase", "bravo phrase", ...), their ids in the order added."""
    return [
        db.expressions.add(f"{name} phrase", f"meaning {i}", [f"syn {i}"], [f"ex {i}a", f"ex {i}b"], f"note {i}", f"표현 {i}", setting, "test")
        for i, name in enumerate(NAMES[:n])
    ]


@pytest.fixture
def draft() -> Draft:
    return sample_draft()


@pytest.fixture
def store(tmp_path) -> Database:
    return Database(tmp_path / "s.db")


class FakeHttp:
    """Every outgoing HTTP request lands here: recorded, then answered with `status` and `json`."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.status = 200
        self.json: object = {}

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if isinstance(self.json, str):
            return httpx2.Response(self.status, text=self.json)
        return httpx2.Response(self.status, json=self.json)

    def sent(self, i: int = 0) -> dict:
        return json.loads(self.requests[i].content)


@pytest.fixture
def http(monkeypatch) -> FakeHttp:
    fake = FakeHttp()
    monkeypatch.setattr("app.net.TRANSPORT", httpx2.MockTransport(fake.answer))
    return fake
