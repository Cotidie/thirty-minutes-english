import json

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import LOGIN_COOKIE
from app.db import Database
from app.generation.generator import VOCABULARY_COUNT
from app.models import ArticleDraft, Draft, ParagraphPictureDraft, PictureDraft, Question, SentencePair, Source, Topic, User, VocabularyDraft
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
            picture=PictureDraft(scene="A tram stop in the rain at dusk, two students under one umbrella.", caption="Waiting for the tram."),
            paragraph_picture=ParagraphPictureDraft(after=2, scene="A driver waves two students onto the last tram.", caption="Boarding the last tram."),
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


def add_user(db: Database, email: str = "a@example.com", *, admin: bool = False, can_create: bool = False) -> User:
    """An account whose password nothing can check, for tests that log in through a token."""
    user = db.accounts.create(email, "no password")
    with db.connect() as conn:
        conn.execute("UPDATE users SET is_admin = ?, can_create = ? WHERE id = ?", (int(admin), int(can_create), user.id))
    result = db.accounts.get(user.id)
    assert result is not None
    return result


def sign_in(client: TestClient, db: Database, user: User) -> None:
    client.cookies.set(LOGIN_COOKIE, db.accounts.start_login(user.id))


def admin_client(app: FastAPI) -> TestClient:
    """A client logged in as the admin, for tests of what a route does rather than who may call it."""
    db = app.state.db
    client = TestClient(app)
    sign_in(client, db, db.accounts.by_email("admin@example.com") or add_user(db, "admin@example.com", admin=True))
    return client


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
