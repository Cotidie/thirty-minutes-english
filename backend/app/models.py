from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Category(StrEnum):
    """Where a topic comes from: a curated field, the day's news, or typed in for one session (never
    suggested). Drives the chip colour on the home page."""

    CS = "cs"
    IE = "ie"
    AI = "ai"
    LITERATURE = "literature"
    HISTORY = "history"
    WORLD = "world"
    KOREA = "korea"
    RESEARCH = "research"
    NEWS = "news"
    TYPED = "typed"


# Not curated: the pool deals from every other category.
UNCURATED = (Category.NEWS, Category.TYPED)


# What each category is called in the key under the chips, in the order the key lists them.
CATEGORY_LABELS: dict[Category, str] = {
    Category.NEWS: "In the news",
    Category.KOREA: "Korea",
    Category.RESEARCH: "Research",
    Category.CS: "Computer science",
    Category.IE: "Industrial engineering",
    Category.AI: "AI",
    Category.LITERATURE: "Literature",
    Category.HISTORY: "History",
    Category.WORLD: "World",
}


class Topic(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    category: Category


class Expression(BaseModel):
    """One expression of the corpus; a session teaches a few of them."""

    id: int
    phrase: str
    meaning: str
    """Plainer words for the same meaning."""
    synonyms: list[str] = []
    usage_note: str
    examples: list[str]
    """The Korean equivalent, hidden behind a chip until tapped."""
    korean: str | None = None
    """Where it is said: casual, workplace or discussion; None when the source does not say."""
    setting: str | None = None


class CorpusEntry(Expression):
    """An expression as the corpus keeps it: where it came from and the sessions that used it."""

    """The post it was read from."""
    source: str
    added_at: str
    """Ids of the sessions that taught it, oldest first."""
    sessions: list[int] = []
    """Ids of the sessions it was swapped out of, oldest first; those count as using it too."""
    swapped: list[int] = []


class Question(BaseModel):
    text: str
    evidence: list[str] = []


class Source(BaseModel):
    title: str
    url: str


class SentencePair(BaseModel):
    """One sentence of the body, copied exactly, and its Korean."""

    en: str
    ko: str


class FigureDraft(BaseModel):
    """An image the generator saw on a page it drew on, to show under paragraph `after` (counted from 1)."""

    after: int
    image_url: str
    page_url: str
    credit: str = ""
    caption: str


class PictureDraft(BaseModel):
    """A drawable moment from the article, drawn only when no source image could be kept."""

    after: int = 1
    scene: str
    caption: str = ""


class ArticleDraft(BaseModel):
    """The article as the generator writes it: one body, its paragraphs split by blank lines."""

    title: str
    body: str
    questions: list[Question]
    sources: list[Source] = []
    translation: list[SentencePair] = []
    figures: list[FigureDraft] = []
    picture: PictureDraft | None = None

    @model_validator(mode="after")
    def keep_only_sentences_found_in_the_body(self) -> "ArticleDraft":
        """A pair the reader cannot click on is no use; the sentence stays English."""
        self.translation = [pair for pair in self.translation if pair.en.strip() and pair.en.strip() in self.body]
        return self


class Paragraph(BaseModel):
    """One paragraph of a stored article; readings and summaries point at it by id."""

    id: int
    text: str


class Figure(BaseModel):
    """An image shown under a paragraph: one from a page the article drew on (with its page and credit),
    or one drawn for the article (neither)."""

    id: int
    paragraph_id: int
    """{picture id}.png, served at /api/images/{image}."""
    image: str
    caption: str
    source_url: str | None = None
    credit: str | None = None


class Article(BaseModel):
    """The article as stored: its paragraphs in order, each with its id, and the figures under them."""

    title: str
    paragraphs: list[Paragraph]
    questions: list[Question]
    sources: list[Source] = []
    translation: list[SentencePair] = []
    figures: list[Figure] = []


class VocabularyDraft(BaseModel):
    """A word as the generator writes it, before it is stored or drawn."""

    word: str
    pos: str
    definition: str
    """Plainer words for the same sense; shown with the definition."""
    synonyms: list[str] = []
    example: str
    """The Korean equivalent in the sense used here; hidden on the card until tapped."""
    korean: str | None = None
    """A drawable situation the word fits, written with the session; drawn for the card."""
    scene: str | None = None
    """One or two sentences on what the picture shows and why it is the word; hidden until asked for."""
    caption: str | None = None


class VocabularyItem(VocabularyDraft):
    """A stored word; stars and practice sentences point at it by id."""

    id: int
    """The scene drawn, for the learner to describe in Practice: {picture id}.png, served at /api/images/{image}."""
    image: str | None = None
    """The example sentence drawn; the picture the card opens on."""
    example_image: str | None = None


class Draft(BaseModel):
    """What the generator writes for a topic. The expressions come from the corpus, not from here."""

    topic: str
    article: ArticleDraft
    vocabulary: list[VocabularyDraft]


class SessionContent(BaseModel):
    topic: str
    expressions: list[Expression]
    article: Article
    vocabulary: list[VocabularyItem]


class SessionSummary(BaseModel):
    id: int
    created_at: datetime
    topic: str
    title: str


class Session(BaseModel):
    id: int
    created_at: datetime
    topic: str
    content: SessionContent


class Stars(BaseModel):
    """What the pair starred in a session: expression ids and word (vocabulary) ids."""

    expressions: list[int] = []
    words: list[int] = []


class Note(BaseModel):
    """The pair's free-form notes on a session, saved whole on every edit."""

    text: str = ""


class TopicEntry(Topic):
    """A topic as the database keeps it: the days it led the news and the sessions written on it."""

    id: int
    added_at: str
    """Days it was among the day's news, oldest first."""
    news_days: list[str] = []
    """Ids of the sessions written on it, oldest first."""
    sessions: list[int] = []


class TopicLibrary(BaseModel):
    """Every topic, for the database page, with every category's name (typed-in ones too)."""

    topics: list[TopicEntry]
    labels: dict[Category, str] = CATEGORY_LABELS | {Category.TYPED: "Typed in"}


class TopicListing(BaseModel):
    """The day's suggestions, whether the news half is still on its way, and why the last fetch failed."""

    topics: list[Topic]
    pending: bool
    error: str | None = None
    labels: dict[Category, str] = CATEGORY_LABELS


class ExampleFeedback(BaseModel):
    """The sentence the native way, and a short line per change made, in order of weight."""

    paraphrase: str
    feedback: list[str]


class SummaryFix(BaseModel):
    """One weakness in how the reader said it: their words and the better ones.
    Records kept before the fixed format also carry a `why`, which is dropped on read."""

    said: str
    better: str


class SummaryFeedback(BaseModel):
    """A spoken summary judged against its paragraph."""

    """The one key point left out or got wrong; empty when the summary holds."""
    missed: list[str]
    fixes: list[SummaryFix]
    """A model answer: what the reader said, cut to one or two short sentences."""
    summary: str


class Sound(BaseModel):
    """One sound of a word as the assessor scored it."""

    phoneme: str
    score: float
    weak: bool
    """The sound heard instead, when weak and another fit better."""
    heard: str | None = None


class Correction(BaseModel):
    """One word the assessor stopped the reader on, and the sound heard in its place.
    `at`, `score` and `sounds` put it back on the paragraph as a mark; readings kept
    before the marks were saved lack them and stay off the page."""

    word: str
    heard: str
    fix: str
    repeated_ok: bool = False
    """Where the word sits in the paragraph, counted in words; -1 when not known."""
    at: int = -1
    score: float = 0
    sounds: list[Sound] = Field(default_factory=list)


class Reading(BaseModel):
    id: int
    created_at: datetime
    paragraph_id: int
    user_text: str
    seconds: float
    corrections: list[Correction] | None = None


class Summary(BaseModel):
    """One paragraph the reader summed up out loud, and what the coach made of it."""

    id: int
    created_at: datetime
    paragraph_id: int
    user_text: str
    feedback: SummaryFeedback
    seconds: float


class Example(BaseModel):
    """One sentence a reader made with an expression or a word (exactly one of the two ids), and the coach's echo of it."""

    id: int
    created_at: datetime
    expression_id: int | None = None
    vocabulary_id: int | None = None
    user_text: str
    coach_text: str
    seconds: float

