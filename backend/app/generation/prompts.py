"""What each Claude call of a session's generation is told. Every pass hears who reads the article and how;
the limits come from `readability`, so the prompts and the length check never disagree."""

from app.generation.levels import describe_levels
from app.generation.passes import VOCABULARY_COUNT, ArticleText, ImageCandidate
from app.generation.readability import MAX_SENTENCE_WORDS, NUMBERS_PER_PARAGRAPH, PARAGRAPH_COUNT, PARAGRAPH_WORDS
from app.pictures.scenes import CAPTION_RULES, SCENE_RULES

# The app's own skills, from its local plugin (backend/plugin).
APP_SKILL = "english-session:session-writing"
# Vendored from github.com/blader/humanizer (MIT, v3.1.0) and github.com/hardikpandya/stop-slop (MIT); the article alone goes through them.
HUMANIZER_SKILL = "english-session:humanizer"
STOP_SLOP_SKILL = "english-session:stop-slop"

REPAIR_ACTIVITY = "Fixing sentence and paragraph lengths"

READER = (
    "Who reads this: Korean graduate students at about B2 level. They read the article aloud in turns, "
    "one paragraph each, until the whole article has been read, then discuss it. The article part of the session "
    "lasts ten minutes, reading included. Each sentence must make sense on one reading at speaking pace, and each "
    "paragraph is one person's turn, so the paragraphs stay close in length."
)

CHECK_ITEMS_RULE = """

Earlier sessions already taught some words. Before you finalize, call check_items with every \
vocabulary word you chose. Replace each one it reports as already taught with a fresh word, then call \
it again with the replacements until it reports nothing."""

_SESSION = (
    "Topics rotate across computer science, industrial engineering, economics, AI, literature, world history, "
    "world affairs, Korean society, travel, and research life; treat each as a general-interest subject, not a specialist one."
)

_RETURN = "Return only the structured output."

_DRAFT = """Before writing, invoke the {app_skill} skill with the Skill tool and follow its instructions.

You are writing the article for a 30-minute English conversation practice session. {session}

{reader}

Today's article topic: {topic}

Write a draft of a short article for a smart general reader. Later passes shorten its sentences and polish it, \
but write to these limits from the start. {limits}

Run at most 3 web searches, with firecrawl_search first and WebSearch only when firecrawl_search fails or finds \
nothing usable, to ground the article in accurate, current facts, and prefer a recent development or debate as the \
angle; never invent specifics you did not verify. Use a number only when the argument needs it, rounded the way a \
person would say it aloud. In sources, list only the web pages you actually drew on (page title and exact URL from \
the search results); leave it empty if you used none. Take a clear angle so there is something to discuss.

Then give images: up to 4 images you saw on the pages you drew on (firecrawl_scrape with the images format lists \
a page's images): a photo of the place, people, or thing, a diagram, or a map. Never a logo, ad, icon, author photo, \
or tracking pixel. Look through every page you drew on before giving fewer than 2. Put first the one that best shows \
what the whole article is about (often the lead photo of the main source). For each give image_url (the exact image \
address from the page), page_url (the page it was on), credit (the outlet or photographer the page names), and shows \
(one plain sentence on what the image shows). Leave images empty when no such image turned up.

Use American English. {done}"""

_EDIT = """You are editing a short article so that it reads well aloud. {reader}

Edit the title and body below and return the whole article.

1. Sentences: at most {max_words} words each. One idea per sentence. At most one inserted phrase per sentence \
(an appositive, a parenthesis, or a clause set off by commas). Keep the subject close to its verb. Split a long \
sentence where its ideas divide, and keep the pieces connected so the paragraph does not read like a list of short claims.
2. Numbers: keep only the ones the angle needs, at most {numbers} per paragraph, not counting a bare year. Round \
them the way a person would say them aloud: "about 150 theaters", "nearly a third", "in 2022". Keep an exact figure \
only when the exactness is the point. Give the day of a date only when the day matters to the story; otherwise give \
the year, or the month and year. Drop times of day unless they matter. A rounded figure must stay true: 153 becomes \
"about 150", never "nearly 200".
3. Names: keep the names the reader needs to follow the argument. A person named once whose name the claim does \
not need becomes their role ("a historian").
4. Paragraphs: {paragraphs_low} to {paragraphs_high} paragraphs separated by blank lines, each {words_low} to \
{words_high} words. Each paragraph is one step of the argument and one reader's turn. Move, merge, or trim sentences \
to even them out.
5. Facts: you may drop, round, or reorder facts. Never add a fact, name, number, date, quote, or source.
6. Keep the angle stated early, the strongest case for one side, one concrete cost or objection, and an ending that \
does not settle the question.
7. Words: prefer the common word a B2 reader knows.

{article}

{done}"""

_POLISH = """{reader}

Run the {humanizer} skill and then the {stop_slop} skill on the title and body below, in embedded mode: return \
only the final text. The article is a factual, third-person news piece, so its voice stays neutral and plain.

Keep the limits the article already meets. {limits} Never add a fact, name, number, date, quote, or source, and \
keep every fact that is there. Keep the paragraphs as they are divided.

Where the skills ask for something these limits forbid, the limits win:
- "Be specific" means naming the actor and the thing. It never means adding a number, name, or date.
- Do not address the reader as "you" and do not put the reader in the scene; the article stays in the third person.
- Cut filler adverbs only, not every adverb.
- Vary sentence length within the {max_words}-word limit.

{article}

{done}"""

_REPAIR = """{reader}

The article below breaks some of these limits. {limits}

Fix only these problems:
{problems}

Split each long sentence where its ideas divide. Bring each paragraph into range by moving a sentence to a neighbor \
or trimming words. Split or merge paragraphs to reach {paragraphs_low} to {paragraphs_high}. Leave every other \
sentence word for word. Never add a fact, name, number, date, quote, or source. Do not use em dashes. Return the \
whole title and body.

{article}

{done}"""

_FINISH = """Before writing, invoke the {app_skill} skill with the Skill tool and follow its instructions while \
producing every part of the content.

You are preparing material for a 30-minute English conversation practice session between two Korean graduate \
students at roughly B2 level who want to sound natural. {session}

{reader}

Today's article topic: {topic}

The article below is final. Do not change it. Where a part asks you to copy from the article, copy from this text exactly.

{article}

{images}

Produce two parts.

1. article parts: Write 3 discussion questions. Each is one short sentence of at most 14 words, in plain \
conversational wording a friend would ask across a table. No compound questions, no "explain the writer's \
reasoning", no quoting. Questions invite explanation, not yes/no. Example of the right length: "Why does the \
writer call the space race a bad label?" The first two are answered by the article: one on the main claim, one on \
a supporting detail. For each of those two give evidence: 1 or 2 passages copied word for word from the article \
body (exact substrings, 5 to 30 words each, same capitalization and punctuation) that the answer rests on. The \
third is an open question the article does not settle. It asks the two speakers what they think, about something \
two reasonable people would disagree on, and it grows out of the article's angle rather than asking about life in \
general. Its evidence is an empty list. Then give translation: every sentence of the article body, in reading \
order, as pairs. en is the sentence copied character for character from the body, final punctuation included, one \
sentence per pair; never merge or split sentences. ko is that sentence in natural written Korean (해라체, "~다"로 \
끝맺기), translated with its neighbors in mind so the Korean reads well in sequence; keep names, figures, and dates \
as they are. Then give figures: up to 2 of the image candidates above, with image_url, page_url, and credit copied \
exactly. The first is the cover, shown under the title: the image that best shows what the whole article is about \
(often the lead photo of the main source); give it after 0. The second shows what one paragraph says; give it after \
(the paragraph it belongs under, counted from 1). When only one image fits, make it the cover. For each give after, \
image_url, page_url, credit, and caption (one plain sentence on what it shows and why it matters to the article or \
to that paragraph). Leave figures empty when no candidate fits. Always give picture too: one moment that captures \
the whole article and that a photo could capture, in two or three concrete sentences (the place, who is there, what \
they are doing, details a viewer could point at; no text or signs), and a one-sentence caption. It is drawn as the \
cover when no cover image can be used. Always give paragraph_picture as well: a different moment, from one \
paragraph, written the same way, with after (the paragraph it belongs under, counted from 1) and a one-sentence \
caption. It is drawn under that paragraph when no image lands under a paragraph, so that the article always shows \
exactly 2 images.

2. vocabulary: {vocabulary_count} words at CEFR {vocabulary_levels} connected to the topic.{level_spread} Draw from \
the article body where it offers strong candidates, and fill the rest with words a well-read speaker would use when \
discussing this subject even if they do not appear in the article. Prefer words useful across academic and \
professional English over topic-specific jargon; no proper nouns. For each give the word, part of speech, a concise \
learner-dictionary definition, synonyms (1 or 2 more common words that could replace it in this sense), one example \
sentence different from the article, korean (the Korean equivalent in the sense used here, one or two words, no \
explanation), a scene: {scene_rules}, and a caption for the scene: {caption_rules}. Vary the scenes across the \
words: different places, times of day, and kinds of people, so no two look alike.

Set topic to the article topic. Use American English. {done}"""


def limits() -> str:
    """The readability limits in one sentence each, as every writing pass quotes them."""
    paragraphs_low, paragraphs_high = PARAGRAPH_COUNT
    words_low, words_high = PARAGRAPH_WORDS
    return (
        f"Limits: every sentence at most {MAX_SENTENCE_WORDS} words. {paragraphs_low} to {paragraphs_high} paragraphs "
        f"separated by blank lines, each {words_low} to {words_high} words. At most {NUMBERS_PER_PARAGRAPH} figures per "
        "paragraph, not counting a bare year."
    )


def draft_prompt(topic: str) -> str:
    """The first pass: research the topic, draft the article, collect images it could show."""
    return _DRAFT.format(app_skill=APP_SKILL, session=_SESSION, reader=READER, topic=topic, limits=limits(), done=_RETURN)


def edit_prompt(text: ArticleText) -> str:
    """The second pass: short sentences, round numbers, paragraphs of one reader's turn each."""
    paragraphs_low, paragraphs_high = PARAGRAPH_COUNT
    words_low, words_high = PARAGRAPH_WORDS
    return _EDIT.format(
        reader=READER,
        max_words=MAX_SENTENCE_WORDS,
        numbers=NUMBERS_PER_PARAGRAPH,
        paragraphs_low=paragraphs_low,
        paragraphs_high=paragraphs_high,
        words_low=words_low,
        words_high=words_high,
        article=_article(text),
        done=_RETURN,
    )


def polish_prompt(text: ArticleText) -> str:
    """The third pass: the humanizer and stop-slop skills, held to the limits the edit met."""
    return _POLISH.format(
        reader=READER,
        humanizer=HUMANIZER_SKILL,
        stop_slop=STOP_SLOP_SKILL,
        limits=limits(),
        max_words=MAX_SENTENCE_WORDS,
        article=_article(text),
        done=_RETURN,
    )


def repair_prompt(text: ArticleText, problems: list[str]) -> str:
    """One extra call when the polished article still breaks a limit: fix the named places only."""
    paragraphs_low, paragraphs_high = PARAGRAPH_COUNT
    return _REPAIR.format(
        reader=READER,
        limits=limits(),
        problems=_bullets(problems),
        paragraphs_low=paragraphs_low,
        paragraphs_high=paragraphs_high,
        article=_article(text),
        done=_RETURN,
    )


def finish_prompt(topic: str, text: ArticleText, images: list[ImageCandidate], levels: tuple[str, ...], check_items: bool) -> str:
    """The last pass: everything copied from the final article, the figures placed, and the words."""
    prompt = _FINISH.format(
        app_skill=APP_SKILL,
        session=_SESSION,
        reader=READER,
        topic=topic,
        article=_article(text),
        images=_candidates(images),
        vocabulary_count=VOCABULARY_COUNT,
        vocabulary_levels=_named(levels),
        level_spread=_spread(levels),
        scene_rules=SCENE_RULES,
        caption_rules=CAPTION_RULES,
        done=_RETURN,
    )
    return prompt + CHECK_ITEMS_RULE if check_items else prompt


def _article(text: ArticleText) -> str:
    return f"Title: {text.title}\n\nBody:\n{text.body}"


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _candidates(images: list[ImageCandidate]) -> str:
    if not images:
        return "Image candidates: none."
    lines = [f"image_url: {i.image_url}; page_url: {i.page_url}; credit: {i.credit}; shows: {i.shows}" for i in images]
    return "Image candidates from the pages the article drew on:\n" + _bullets(lines)


def _named(levels: tuple[str, ...]) -> str:
    """"level B1", or "levels B2, B2+ and C1"."""
    return f"level {levels[0]}" if len(levels) == 1 else f"levels {describe_levels(levels)}"


def _spread(levels: tuple[str, ...]) -> str:
    """With more than one level, the words are shared out among them."""
    return " Spread them about evenly across these levels." if len(levels) > 1 else ""
