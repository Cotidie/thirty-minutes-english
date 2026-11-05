from app.generation.readability import MAX_SENTENCE_WORDS, PARAGRAPH_COUNT, PARAGRAPH_WORDS, paragraphs, problems, sentences, word_count
from tests.conftest import readable_body


def test_the_limits_are_the_ones_the_spec_sets():
    assert (MAX_SENTENCE_WORDS, PARAGRAPH_COUNT, PARAGRAPH_WORDS) == (20, (4, 5), (50, 65))


def test_sentences_end_at_marks_and_closing_quotes():
    assert sentences('Maldonado said it is "difficult." Then he left. Was it right?') == [
        'Maldonado said it is "difficult."', "Then he left.", "Was it right?",
    ]


def test_abbreviations_and_decimals_do_not_end_a_sentence():
    text = "The U.S. Ambassador wrote at 1:30 a.m. that 3.80 was low. Dr. Kim agreed."
    assert sentences(text) == ["The U.S. Ambassador wrote at 1:30 a.m. that 3.80 was low.", "Dr. Kim agreed."]


def test_a_hyphenated_word_counts_once():
    assert word_count("A U.S.-based, 13-episode run.") == 4


def test_paragraphs_split_on_blank_lines_even_with_spaces_in_them():
    assert paragraphs("One.\n\n\nTwo.\n  \nThree.\n") == ["One.", "Two.", "Three."]


def test_a_readable_body_has_no_problems():
    assert problems(readable_body()) == []
    assert problems(readable_body(paragraphs=5)) == []


def test_problems_name_the_paragraph_count_each_long_sentence_and_each_paragraph_out_of_range():
    long = " ".join(["Long"] + ["word"] * 24) + "."  # 25 words
    fill = " ".join(["Fill"] + ["word"] * 29) + "."  # 30 words
    short = " ".join(["Short"] + ["word"] * 39) + "."  # 40 words, one sentence
    body = "\n\n".join([readable_body(paragraphs=1), long + " " + fill, short])
    assert problems(body) == [
        "The article has 3 paragraphs (range 4 to 5).",
        f'Sentence of 25 words (limit 20): "{long}"',
        f'Sentence of 30 words (limit 20): "{fill}"',
        f'Sentence of 40 words (limit 20): "{short}"',
        "Paragraph 3 has 40 words (range 50 to 65).",
    ]
