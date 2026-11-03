"""The CEFR levels a session's words are drawn from, with the official plus levels between B1 and C2."""

LEVELS: tuple[str, ...] = ("B1", "B1+", "B2", "B2+", "C1", "C2")
LEVEL_LABELS: dict[str, str] = {
    "B1": "Intermediate",
    "B1+": "Strong intermediate",
    "B2": "Upper intermediate",
    "B2+": "Strong upper intermediate",
    "C1": "Advanced",
    "C2": "Proficient",
}
DEFAULT_LEVELS: tuple[str, ...] = ("B2", "B2+", "C1")


def parse_levels(value: str) -> tuple[str, ...]:
    """The known levels the value names, in LEVELS order; DEFAULT_LEVELS when it names none.
    Lenient on purpose: a value from the environment never went through the settings check."""
    named = {piece.strip().upper() for piece in value.split(",")}
    return tuple(level for level in LEVELS if level in named) or DEFAULT_LEVELS


def describe_levels(levels: tuple[str, ...]) -> str:
    """How the prompt names the levels: "B1", "B2 to C1" for a run, "B1 and C1" or "B1, C1 and C2" with gaps."""
    if len(levels) == 1:
        return levels[0]
    if _is_run(levels):
        return f"{levels[0]} to {levels[-1]}"
    return f"{', '.join(levels[:-1])} and {levels[-1]}"


def _is_run(levels: tuple[str, ...]) -> bool:
    """Whether the levels sit next to each other in LEVELS, with none between them left out."""
    start = LEVELS.index(levels[0])
    return levels == LEVELS[start : start + len(levels)]
