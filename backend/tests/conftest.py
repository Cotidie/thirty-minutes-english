import pytest

from app.generation.generator import EXPRESSION_COUNT, VOCABULARY_COUNT
from app.models import Article, Expression, Question, SessionContent, VocabularyItem


def sample_content(topic: str = "Digital twins", title: str = "Twins at Work") -> SessionContent:
    return SessionContent(
        topic=topic,
        expressions=[
            Expression(
                phrase=f"phrase {i}",
                meaning=f"meaning {i}",
                usage_note=f"note {i}",
                examples=[f"ex {i}a", f"ex {i}b"],
            )
            for i in range(EXPRESSION_COUNT)
        ],
        article=Article(
            title=title,
            body="A body with the word ubiquitous in it.",
            questions=[Question(text=q) for q in ("q1", "q2", "q3")],
        ),
        vocabulary=[
            VocabularyItem(word=f"word{i}", pos="noun", definition=f"def {i}", example=f"ex {i}", scene=f"scene {i}")
            for i in range(VOCABULARY_COUNT)
        ],
    )


@pytest.fixture
def content() -> SessionContent:
    return sample_content()
