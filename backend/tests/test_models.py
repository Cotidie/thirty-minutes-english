from app.generator import SESSION_SCHEMA
from app.models import Article, Question


def test_article_accepts_legacy_string_questions():
    article = Article(title="T", body="Body text.", questions=["Why?"])
    assert article.questions == [Question(text="Why?", evidence=[])]


def test_article_accepts_question_objects():
    article = Article(title="T", body="Body text.", questions=[{"text": "Why?", "evidence": ["Body text."]}])
    assert article.questions[0].evidence == ["Body text."]


def test_schema_requires_evidence_per_question():
    question_schema = SESSION_SCHEMA["properties"]["article"]["properties"]["questions"]["items"]
    assert set(question_schema["required"]) == {"text", "evidence"}
    assert question_schema["properties"]["evidence"]["minItems"] >= 1


def test_article_sources_default_to_empty_for_legacy_content():
    from app.models import Article

    a = Article.model_validate({"title": "t", "body": "b", "questions": ["q"]})
    assert a.sources == []
