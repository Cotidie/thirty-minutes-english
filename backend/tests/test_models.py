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


def test_correction_kind_defaults_to_pronunciation_for_old_records():
    from app.models import Correction

    old = Correction.model_validate({"word": "verified", "heard": "berified", "fix": "V"})
    assert old.kind == "pronunciation"
    new = Correction.model_validate({"kind": "phrasing", "word": "twice as long", "heard": "twice as / long", "fix": "one piece"})
    assert new.kind == "phrasing"


def test_translation_keeps_only_pairs_whose_sentence_is_in_the_body():
    a = Article.model_validate(
        {
            "title": "t",
            "body": "First one. Second one.",
            "questions": [],
            "translation": [
                {"en": "First one.", "ko": "첫 번째다."},
                {"en": "Not in the body.", "ko": "본문에 없다."},
                {"en": " Second one. ", "ko": "두 번째다."},
            ],
        }
    )
    assert [p.ko for p in a.translation] == ["첫 번째다.", "두 번째다."]
    assert Article.model_validate({"title": "t", "body": "b", "questions": []}).translation == []


def test_schema_and_prompt_ask_for_a_sentence_by_sentence_translation():
    from app.generator import PROMPT_TEMPLATE

    article = SESSION_SCHEMA["properties"]["article"]
    assert "translation" in article["required"]
    assert set(article["properties"]["translation"]["items"]["required"]) == {"en", "ko"}
    assert "copied character for character" in PROMPT_TEMPLATE
    assert "never merge or split sentences" in PROMPT_TEMPLATE
