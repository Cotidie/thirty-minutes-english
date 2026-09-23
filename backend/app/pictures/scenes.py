"""What each vocabulary picture shows: the rules a scene follows, and a writer for a fresh one."""

import random
from dataclasses import dataclass

from app.llm import Claude, GenerationError, Runner
from app.models import VocabularyItem

# What a scene is, for the session generator and the redraw writer alike.
SCENE_RULES = """two or three sentences describing one drawable moment where a fluent speaker would reach \
for the word, so that a learner shown a picture of it would describe it with the word. Name the place, who \
is there and what they are doing, and three or four supporting details a viewer could point at: objects, \
weather, time of day, what is going on in the background. Physical and specific ("a single toll booth open \
on a wide highway at dusk, a line of cars backed up behind it, a driver leaning out of a window, a cyclist \
slipping past on the shoulder"), never abstract, and nothing that needs written words in the picture"""

SCENE_SCHEMA: dict = {"type": "object", "additionalProperties": False, "required": ["scene"], "properties": {"scene": {"type": "string"}}}

SCENE_PROMPT = """A learner will be shown a picture and asked to describe it in one sentence using this word:

Word: {word} ({pos})
Meaning: {definition}
Example: {example}

Write a new scene for the picture: {rules}.

Start from this spark and build the scene around it; swap any part that does not fit the word, but keep \
its flavour so the scene is fresh: {spark}.
It must differ clearly from this earlier scene, which the learner has already seen: {previous}

Return only the structured output."""

# Rolled per redraw so the writer, which otherwise settles on its favourite scene
# for a word, starts somewhere new each time.
PLACES = (
    "a crowded family kitchen", "a factory floor between shifts", "a hospital corridor", "an open-plan office",
    "a street market", "a train platform", "a school classroom", "a construction site", "a farm at harvest",
    "a small repair shop", "an airport gate", "a living room during a party", "a city park on a weekend",
    "a fishing harbour", "a laboratory bench", "a mountain trail", "a supermarket checkout", "a football pitch",
    "a hotel lobby", "a rooftop", "a courtroom", "a wedding hall", "a bus stuck in traffic", "a night market",
    "a village square", "a shipping warehouse", "a dentist's waiting room", "a campsite", "a subway car", "a bakery at opening time",
)
MOMENTS = (
    "early morning light", "pouring rain", "late at night under artificial light", "a heatwave afternoon",
    "the first snow of the year", "golden hour", "a power cut", "the minute before a deadline", "a public holiday",
    "thick fog", "the middle of a storm", "the last hour before closing",
)
TWISTS = (
    "a child watching closely", "a dog getting in the way", "something has just gone wrong", "someone in a hurry",
    "a crowd looking on", "an old and a new version side by side", "an elderly person and a teenager together",
    "a visitor who does not belong there", "a phone held up, filming", "far too many of one thing",
    "one person doing the job of three", "a celebration nobody expected",
)


@dataclass(frozen=True)
class Spark:
    """A random starting point for a scene: where, when, and one thing that makes it a story."""

    place: str
    moment: str
    twist: str

    @classmethod
    def roll(cls, rng: random.Random) -> "Spark":
        return cls(rng.choice(PLACES), rng.choice(MOMENTS), rng.choice(TWISTS))

    def __str__(self) -> str:
        return f"place: {self.place}; moment: {self.moment}; twist: {self.twist}"


class SceneWriter:
    """A fresh scene for one word, from a short text run of the claude CLI seeded with a random Spark."""

    def __init__(self, cli: Runner, rng: random.Random | None = None) -> None:
        self._cli = cli
        self._rng = rng or random.Random()

    @classmethod
    def with_cli(cls, model: str) -> "SceneWriter":
        return cls(Claude(model, timeout_s=60))

    def build_prompt(self, item: VocabularyItem, spark: Spark) -> str:
        return SCENE_PROMPT.format(
            word=item.word, pos=item.pos, definition=item.definition, example=item.example,
            rules=SCENE_RULES, spark=spark, previous=item.scene or "none",
        )

    def write(self, item: VocabularyItem) -> str:
        """Raises GenerationError when the run fails or comes back blank."""
        prompt = self.build_prompt(item, Spark.roll(self._rng))
        scene = str(self._cli.run(prompt, SCENE_SCHEMA).get("scene", "")).strip()
        if not scene:
            raise GenerationError("the model wrote no scene")
        return scene
