"""The limits an article meets so that it reads well aloud, one paragraph per reader's turn, and the check
that names where a body breaks them. The prompts quote these limits; the generator checks against them."""

import re

MAX_SENTENCE_WORDS = 20
PARAGRAPH_COUNT = (4, 5)
PARAGRAPH_WORDS = (50, 65)
NUMBERS_PER_PARAGRAPH = 2  # told to the model only; not checked here
# A repair trims a long paragraph or two; losing more than this share of the words means it dropped content.
REPAIR_KEEPS_WORDS = 0.85

# A period after one of these does not end a sentence.
ABBREVIATIONS = ("U.S.", "U.K.", "U.N.", "E.U.", "a.m.", "p.m.", "Dr.", "Mr.", "Mrs.", "Ms.", "St.", "Jr.", "e.g.", "i.e.", "vs.")

# An end mark, any closing quotes or brackets, then space and what can start the next sentence.
_SENTENCE_END = re.compile(r"""[.!?]["'”’)]*(?=\s+["“'(]?[A-Z0-9])""")
_BLANK_LINE = re.compile(r"\n\s*\n")


def word_count(text: str) -> int:
    """Words as a reader sees them: a hyphenated word is one."""
    return len(text.split())


def paragraphs(body: str) -> list[str]:
    """The body's paragraphs, split on blank lines, in reading order."""
    return [part.strip() for part in _BLANK_LINE.split(body) if part.strip()]


def sentences(paragraph: str) -> list[str]:
    """The paragraph's sentences in order. Abbreviations and decimal points do not end one."""
    found: list[str] = []
    start = 0
    for end in _SENTENCE_END.finditer(paragraph):
        piece = paragraph[start : end.end()].strip()
        if piece.split()[-1] in ABBREVIATIONS:
            continue
        found.append(piece)
        start = end.end()
    if rest := paragraph[start:].strip():
        found.append(rest)
    return found


def problems(body: str) -> list[str]:
    """Where the body breaks the limits, one line each: the paragraph count, then each paragraph's
    long sentences and its length, in reading order. Empty when it reads within them."""
    parts = paragraphs(body)
    found = _count_problem(len(parts))
    for number, paragraph in enumerate(parts, 1):
        found += _long_sentences(paragraph) + _length_problem(number, paragraph)
    return found


def repair_holds(before: str, after: str) -> bool:
    """Whether a repaired body may replace `before`: it breaks no more limits, its paragraph count is no farther
    from the range (a merged-away paragraph is a lost turn), and it keeps nearly all of the words (trimming, not cutting)."""
    return (
        len(problems(after)) <= len(problems(before))
        and _count_distance(len(paragraphs(after))) <= _count_distance(len(paragraphs(before)))
        and word_count(after) >= REPAIR_KEEPS_WORDS * word_count(before)
    )


def _count_distance(count: int) -> int:
    low, high = PARAGRAPH_COUNT
    return max(low - count, count - high, 0)


def _count_problem(count: int) -> list[str]:
    low, high = PARAGRAPH_COUNT
    return [] if low <= count <= high else [f"The article has {count} paragraphs (range {low} to {high})."]


def _long_sentences(paragraph: str) -> list[str]:
    return [
        f'Sentence of {word_count(sentence)} words (limit {MAX_SENTENCE_WORDS}): "{sentence}"'
        for sentence in sentences(paragraph)
        if word_count(sentence) > MAX_SENTENCE_WORDS
    ]


def _length_problem(number: int, paragraph: str) -> list[str]:
    low, high = PARAGRAPH_WORDS
    words = word_count(paragraph)
    return [] if low <= words <= high else [f"Paragraph {number} has {words} words (range {low} to {high})."]
