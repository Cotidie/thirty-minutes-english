from app.models import ArticleDraft


def test_translation_keeps_only_pairs_whose_sentence_is_in_the_body():
    a = ArticleDraft.model_validate(
        {
            "title": "t",
            "body": "First one. Second one.",
            "question": "q",
            "translation": [
                {"en": "First one.", "ko": "첫 번째다."},
                {"en": "Not in the body.", "ko": "본문에 없다."},
                {"en": " Second one. ", "ko": "두 번째다."},
            ],
        }
    )
    assert [p.ko for p in a.translation] == ["첫 번째다.", "두 번째다."]
    assert ArticleDraft.model_validate({"title": "t", "body": "b", "question": "q"}).translation == []
