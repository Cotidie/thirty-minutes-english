import pytest

from app.models import Article, Expression, SessionContent, VocabularyItem


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
            for i in range(6)
        ],
        article=Article(
            title=title,
            body="A body with the word ubiquitous in it.",
            questions=["q1", "q2", "q3"],
        ),
        vocabulary=[
            VocabularyItem(word=f"word{i}", pos="noun", definition=f"def {i}", example=f"ex {i}")
            for i in range(12)
        ],
    )


@pytest.fixture
def content() -> SessionContent:
    return sample_content()
