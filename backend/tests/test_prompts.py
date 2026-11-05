import pytest

from app.generation.generator import PLUGIN_DIR
from app.generation.passes import ArticleText, ImageCandidate
from app.generation.prompts import (
    APP_SKILL,
    CHECK_ITEMS_RULE,
    HUMANIZER_SKILL,
    READER,
    STOP_SLOP_SKILL,
    draft_prompt,
    edit_prompt,
    finish_prompt,
    polish_prompt,
    repair_prompt,
)

TEXT = ArticleText(title="Twins at Work", body="First paragraph.\n\nSecond paragraph.")
IMAGE = ImageCandidate(image_url="https://example.com/plant.jpg", page_url="https://example.com", credit="Example", shows="A factory floor.")
LEVELS = ("B2", "B2+", "C1")


def every_prompt() -> list[str]:
    return [
        draft_prompt("Digital twins"),
        edit_prompt(TEXT),
        polish_prompt(TEXT),
        repair_prompt(TEXT, ["Paragraph 1 has 2 words (range 50 to 65)."]),
        finish_prompt("Digital twins", TEXT, [IMAGE], LEVELS, False),
    ]


def test_every_pass_is_told_who_reads_the_article_and_how():
    assert all(READER in prompt for prompt in every_prompt())
    assert "aloud in turns, one paragraph each" in READER


def test_the_edits_carry_the_limits_from_the_readability_constants():
    for prompt in (edit_prompt(TEXT), polish_prompt(TEXT), repair_prompt(TEXT, ["x"])):
        assert "at most 20 words" in prompt and "50 to 65 words" in prompt and "4 to 5 paragraphs" in prompt
    assert "at most 2 per paragraph, not counting a bare year" in edit_prompt(TEXT)
    assert '"about 150 theaters"' in edit_prompt(TEXT) and "Never add a fact" in edit_prompt(TEXT)


def test_the_article_text_goes_into_the_editing_passes():
    for prompt in (edit_prompt(TEXT), polish_prompt(TEXT), repair_prompt(TEXT, ["x"]), finish_prompt("t", TEXT, [], LEVELS, False)):
        assert "Title: Twins at Work" in prompt and "First paragraph.\n\nSecond paragraph." in prompt


def test_the_polish_runs_both_skills_and_says_where_the_limits_win():
    prompt = polish_prompt(TEXT)
    assert prompt.index(HUMANIZER_SKILL) < prompt.index(STOP_SLOP_SKILL)
    assert '"Be specific"' in prompt and "third person" in prompt and "filler adverbs" in prompt and "embedded mode" in prompt


def test_the_repair_names_each_problem_and_leaves_the_rest_alone():
    prompt = repair_prompt(TEXT, ['Sentence of 25 words (limit 20): "Long."', "Paragraph 2 has 70 words (range 50 to 65)."])
    assert '- Sentence of 25 words (limit 20): "Long."\n- Paragraph 2 has 70 words (range 50 to 65).' in prompt
    assert "word for word" in prompt


def test_the_draft_researches_and_collects_images_but_places_nothing():
    prompt = draft_prompt("Digital twins")
    assert f"invoke the {APP_SKILL} skill" in prompt and "Today's article topic: Digital twins" in prompt
    assert "firecrawl_search first" in prompt and "firecrawl_scrape" in prompt and "Never a logo" in prompt
    assert "after 0" not in prompt and "discussion questions" not in prompt and "vocabulary" not in prompt
    assert "Names, dates, numbers" not in prompt and "(dates, names, figures)" not in prompt


def test_the_finish_keeps_the_article_and_picks_figures_from_the_candidates():
    prompt = finish_prompt("Digital twins", TEXT, [IMAGE], LEVELS, False)
    assert "The article below is final. Do not change it." in prompt
    assert "- image_url: https://example.com/plant.jpg; page_url: https://example.com; credit: Example; shows: A factory floor." in prompt
    assert (
        prompt.index("Write 3 discussion questions")
        < prompt.index("Then give translation")
        < prompt.index("Then give figures")
        < prompt.index("Always give picture")
        < prompt.index("2. vocabulary")
    )
    assert "after 0" in prompt and "Image candidates: none." in finish_prompt("t", TEXT, [], LEVELS, False)


def test_the_item_check_rule_rides_only_on_the_finish():
    assert CHECK_ITEMS_RULE in finish_prompt("t", TEXT, [], LEVELS, True)
    assert all(CHECK_ITEMS_RULE not in prompt for prompt in every_prompt())


@pytest.mark.parametrize(
    ("levels", "asked"),
    [
        (("B2", "B2+", "C1"), "8 words at CEFR levels B2, B2+ and C1 connected to the topic. Spread them about evenly across these levels."),
        (("B1",), "8 words at CEFR level B1 connected to the topic. Draw"),
    ],
)
def test_the_words_come_from_every_level_set_by_name(levels, asked):
    assert asked in finish_prompt("t", TEXT, [], levels, False)


def test_stop_slop_is_vendored_unchanged_with_its_license():
    skill = PLUGIN_DIR / "skills" / "stop-slop"
    assert (skill / "SKILL.md").read_text().startswith("---\nname: stop-slop\n")
    assert (skill / "LICENSE").is_file() and "hardikpandya/stop-slop" in (skill / "SOURCE.md").read_text()
    assert all((skill / "references" / name).is_file() for name in ("phrases.md", "structures.md", "examples.md"))


def test_session_writing_no_longer_asks_for_more_numbers():
    text = (PLUGIN_DIR / "skills" / "session-writing" / "SKILL.md").read_text()
    assert "Specific over general" not in text and "Mostly 12 to 22 words" not in text
    assert "aloud in turns, one paragraph each" in text
