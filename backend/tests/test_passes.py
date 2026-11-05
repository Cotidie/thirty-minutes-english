import jsonschema
import pytest

from app.generation.passes import DRAFT_SCHEMA, FINISH_SCHEMA, TEXT_SCHEMA, ArticleText, FirstDraft, Finish, assemble, parse
from app.llm import GenerationError
from tests.conftest import sample_finish, sample_first_draft

CANDIDATE = {"after": 0, "image_url": "https://example.com/plant.jpg", "page_url": "https://example.com", "credit": "Example", "caption": "The plant."}
STRANGER = {**CANDIDATE, "after": 2, "image_url": "https://elsewhere.example/x.jpg"}


def test_sample_payloads_fit_the_schemas_the_model_answers_in():
    jsonschema.validate(sample_first_draft(), DRAFT_SCHEMA)
    jsonschema.validate({"title": "t", "body": "b"}, TEXT_SCHEMA)
    jsonschema.validate(sample_finish([CANDIDATE]), FINISH_SCHEMA)


def test_the_finishing_pass_has_no_way_to_change_the_article():
    assert not {"title", "body", "sources"} & set(FINISH_SCHEMA["properties"])
    assert FINISH_SCHEMA["properties"]["vocabulary"]["minItems"] == FINISH_SCHEMA["properties"]["vocabulary"]["maxItems"] == 8


def test_the_draft_offers_image_candidates_without_placing_them():
    item = DRAFT_SCHEMA["properties"]["images"]["items"]
    assert set(item["required"]) == {"image_url", "page_url", "credit", "shows"} and "after" not in item["properties"]
    assert DRAFT_SCHEMA["properties"]["images"]["maxItems"] == 4


def test_the_session_takes_its_text_from_the_last_edit_its_sources_from_the_draft_and_the_rest_from_the_finish():
    first = parse(FirstDraft, sample_first_draft())
    final = ArticleText(title="Final title", body="Final body.")
    draft = assemble(final, first, parse(Finish, sample_finish([CANDIDATE])))
    assert (draft.article.title, draft.article.body) == ("Final title", "Final body.")
    assert draft.article.sources == first.sources
    assert len(draft.vocabulary) == 8 and draft.article.figures[0].image_url == CANDIDATE["image_url"]


def test_an_image_the_draft_never_saw_is_dropped():
    draft = assemble(ArticleText(title="t", body="b"), parse(FirstDraft, sample_first_draft()), parse(Finish, sample_finish([STRANGER, CANDIDATE])))
    assert [f.image_url for f in draft.article.figures] == [CANDIDATE["image_url"]]


def test_evidence_the_article_view_cannot_find_is_dropped():
    """Kept as the article view marks it: inside one paragraph, any case, trimmed."""
    body = "The plant runs a twin of itself.\n\nEngineers test changes there first."
    finish = sample_finish()
    finish["questions"][0]["evidence"] = [" the plant runs a twin ", "A passage the model made up."]
    finish["questions"][1]["evidence"] = ["of itself. Engineers test"]  # spans two paragraphs
    draft = assemble(ArticleText(title="t", body=body), parse(FirstDraft, sample_first_draft()), parse(Finish, finish))
    assert [q.evidence for q in draft.article.questions[:2]] == [[" the plant runs a twin "], []]


def test_a_payload_that_fails_validation_raises():
    with pytest.raises(GenerationError, match="validation"):
        parse(FirstDraft, {"title": "x"})
