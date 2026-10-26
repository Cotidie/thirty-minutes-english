"""Dealing from the curated topics: the day's slice on the home page, and one for a session asked for
without a topic."""

import random
from collections import defaultdict
from datetime import date

from app.models import Category, Topic


def pool_for_day(day: date, count: int, curated: list[Topic], exclude: list[str] | None = None, salt: int = 0) -> list[Topic]:
    """The same slice all day, a different one tomorrow. Seeded by the date, plus a
    salt so a manual refresh can deal a fresh slice within the day. Dealt one
    category at a time, so every category shows up before any repeats."""
    taken = set(exclude or ())
    rng = random.Random(day.toordinal() * 1000 + salt)
    by_category: dict[Category, list[Topic]] = defaultdict(list)
    for topic in curated:
        if topic.text not in taken:
            by_category[topic.category].append(topic)
    hands = list(by_category.values())
    for hand in hands:
        rng.shuffle(hand)
    rng.shuffle(hands)
    dealt: list[Topic] = []
    while len(dealt) < count and any(hands):
        for hand in hands:
            if hand and len(dealt) < count:
                dealt.append(hand.pop())
    return dealt


def pick_topic(recent: list[str], curated: list[str], rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    unused = [t for t in curated if t not in set(recent)]
    return rng.choice(unused or curated)
