"""Expressions and words already taught, so the next session can avoid them."""

import random
from dataclasses import dataclass, field


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
