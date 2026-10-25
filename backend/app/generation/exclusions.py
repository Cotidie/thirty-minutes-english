"""Words already taught, so the next session can avoid them, and the normalized key that tells close
variants of a word or phrase apart from new ones (the expression corpus uses it too)."""

import random
import re
from dataclasses import dataclass

# Words that make "play the devil's advocate" and "play devil's advocate" the same expression.
FILLER = {"a", "an", "the", "to", "one's", "someone's", "somebody's", "sb", "sth", "something", "someone", "your", "my"}


def key(item: str) -> str:
    """The item reduced to its content words, lower case, for matching close variants."""
    words = re.findall(r"[a-z']+", item.lower().replace("’", "'"))
    return " ".join(w for w in words if w not in FILLER)


@dataclass(frozen=True)
class Exclusions:
    words: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.words)

    def thin(self, keep_probability: float, rng: random.Random | None = None) -> "Exclusions":
        """Drop each word with probability 1 - keep_probability, so a few old ones may return."""
        rng = rng or random.Random()
        return Exclusions(tuple(w for w in self.words if rng.random() < keep_probability))

    def taught(self, words: list[str]) -> list[str]:
        """The candidates that match a word here, close variants included."""
        old = {key(w) for w in self.words}
        return [w for w in words if key(w) in old]
