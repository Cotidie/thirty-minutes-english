from app.config.settings import SPECS

MODELS_WITH_EFFORT = {spec.effort_of for spec in SPECS if spec.effort_of}


def test_a_model_with_an_effort_says_in_words_what_it_is_for():
    uses = {spec.key: spec.use for spec in SPECS if spec.key in MODELS_WITH_EFFORT}
    assert uses == {
        "CLAUDE_MODEL": "Writing sessions",
        "TOPICS_MODEL": "News topics",
        "EXAMPLE_MODEL": "Practice feedback",
        "SUMMARY_MODEL": "Summary judging",
    }


def test_what_such_a_model_does_fits_on_one_line():
    for spec in SPECS:
        if spec.key in MODELS_WITH_EFFORT:
            assert len(spec.help) <= 50, spec.key
