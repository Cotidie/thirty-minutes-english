from app.models import Article


def test_article_accepts_question_objects():
    article = Article(title="T", body="Body text.", questions=[{"text": "Why?", "evidence": ["Body text."]}])
    assert article.questions[0].evidence == ["Body text."]


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
