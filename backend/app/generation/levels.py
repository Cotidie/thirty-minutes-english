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


def describe_levels(levels: tuple[str, ...]) -> str:
    """Every level by name, so none hides inside a range: "B1", "B2 and C1", "B2, B2+ and C1"."""
    if len(levels) == 1:
        return levels[0]
    return f"{', '.join(levels[:-1])} and {levels[-1]}"
