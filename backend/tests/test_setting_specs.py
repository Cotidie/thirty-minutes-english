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


def test_the_text_on_such_a_row_reads_as_two_sentences_at_most_four():
    efforts = {spec.effort_of: spec for spec in SPECS if spec.effort_of}
    for spec in SPECS:
        if spec.key in MODELS_WITH_EFFORT:
            assert spec.help.endswith(".") and efforts[spec.key].help.endswith(".")
            assert not efforts[spec.key].help.startswith("How much")
