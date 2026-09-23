import json

import httpx2
import pytest

from app.generation.generator import EXPRESSION_COUNT, VOCABULARY_COUNT
from app.models import (
    Article,
    Expression,
    Question,
    SentencePair,
    SessionContent,
    Source,
    VocabularyItem,
)


def sample_content(topic: str = "Digital twins", title: str = "Twins at Work") -> SessionContent:
    return SessionContent(
        topic=topic,
        expressions=[
            Expression(
                phrase=f"phrase {i}",
                meaning=f"meaning {i}",
                usage_note=f"note {i}",
                examples=[f"ex {i}a", f"ex {i}b"],
                korean=f"표현 {i}",
            )
            for i in range(EXPRESSION_COUNT)
        ],
        article=Article(
            title=title,
            body="A body with the word ubiquitous in it.",
            questions=[
                Question(text="q1", evidence=["the word ubiquitous"]),
                Question(text="q2", evidence=["A body"]),
                Question(text="q3"),
            ],
            sources=[Source(title="A page", url="https://example.com")],
            translation=[SentencePair(en="A body with the word ubiquitous in it.", ko="어디에나 있다는 단어가 든 본문이다.")],
        ),
        vocabulary=[
            VocabularyItem(word=f"word{i}", pos="noun", definition=f"def {i}", example=f"ex {i}", korean=f"단어 {i}", scene=f"scene {i}")
            for i in range(VOCABULARY_COUNT)
        ],
    )


@pytest.fixture
def content() -> SessionContent:
    return sample_content()


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
