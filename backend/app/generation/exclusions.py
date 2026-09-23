"""Expressions and words already taught, so the next session can avoid them."""

import random
import re
from dataclasses import dataclass, field

# Words that make "play the devil's advocate" and "play devil's advocate" the same expression.
FILLER = {"a", "an", "the", "to", "one's", "someone's", "somebody's", "sb", "sth", "something", "someone", "your", "my"}


def key(item: str) -> str:
    """The item reduced to its content words, lower case, for matching close variants."""
    words = re.findall(r"[a-z']+", item.lower().replace("’", "'"))
    return " ".join(w for w in words if w not in FILLER)


@dataclass(frozen=True)
class Exclusions:
    expressions: tuple[str, ...] = field(default_factory=tuple)
    words: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return bool(self.expressions or self.words)

    def thin(self, keep_probability: float, rng: random.Random | None = None) -> "Exclusions":
        """Drop each item with probability 1 - keep_probability, so a few old items may return."""
        rng = rng or random.Random()
        return Exclusions(
            expressions=tuple(e for e in self.expressions if rng.random() < keep_probability),
            words=tuple(w for w in self.words if rng.random() < keep_probability),
        )

    def taught(self, expressions: list[str], words: list[str]) -> list[str]:
        """The candidates that match an item here, close variants included."""
        old_expressions = {key(e) for e in self.expressions}
        old_words = {key(w) for w in self.words}
        return [e for e in expressions if key(e) in old_expressions] + [w for w in words if key(w) in old_words]
