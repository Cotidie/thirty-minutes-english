import random
from datetime import date

from app.topics.pool import (
    POOLS,
    TOPICS,
    pick_topic,
    pool_for_day,
)

TEXTS = tuple(t.text for t in TOPICS)


def test_pick_topic_avoids_recent():
    recent = list(TEXTS[:-1])
    assert pick_topic(recent, rng=random.Random(0)) == TEXTS[-1]


def test_pick_topic_falls_back_when_all_recent():
    assert pick_topic(list(TEXTS), rng=random.Random(0)) in TEXTS


def test_pick_topic_is_random_among_unused():
    picks = {pick_topic([], rng=random.Random(seed)) for seed in range(50)}
    assert len(picks) > 1


def test_a_day_shows_every_domain_before_repeating_one():
    dealt = pool_for_day(date(2026, 9, 21), 9)
    categories = [t.category for t in dealt]
    assert set(categories[:8]) == {p[0].category for p in POOLS}
    assert len(dealt) == 9
