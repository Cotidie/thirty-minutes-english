from app.generator import SESSION_SCHEMA
from app.models import Article, Question


def test_article_accepts_legacy_string_questions():
    article = Article(title="T", body="Body text.", questions=["Why?"])
    assert article.questions == [Question(text="Why?", evidence=[])]


def test_article_accepts_question_objects():
    article = Article(title="T", body="Body text.", questions=[{"text": "Why?", "evidence": ["Body text."]}])
    assert article.questions[0].evidence == ["Body text."]


def test_schema_asks_for_evidence_but_lets_the_open_question_have_none():
    question_schema = SESSION_SCHEMA["properties"]["article"]["properties"]["questions"]["items"]
    assert set(question_schema["required"]) == {"text", "evidence"}
    assert question_schema["properties"]["evidence"]["maxItems"] == 2
    assert question_schema["properties"]["evidence"]["minItems"] == 0


def test_article_sources_default_to_empty_for_legacy_content():
    from app.models import Article

    a = Article.model_validate({"title": "t", "body": "b", "questions": ["q"]})
    assert a.sources == []
