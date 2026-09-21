import random
from datetime import date

from app.models import Category
from app.topics import (
    AI_TOPICS,
    CS_TOPICS,
    HISTORY_TOPICS,
    IE_TOPICS,
    KOREA_TOPICS,
    LITERATURE_TOPICS,
    POOLS,
    RESEARCH_TOPICS,
    TOPICS,
    WORLD_TOPICS,
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


def test_topics_span_eight_domains():
    assert len(POOLS) == 8
    assert set(TOPICS) == set().union(*(set(p) for p in POOLS))
    assert min(len(p) for p in POOLS) >= 40
    assert len(set(TEXTS)) == len(TEXTS)


def test_a_day_shows_every_domain_before_repeating_one():
    dealt = pool_for_day(date(2026, 9, 21), 9)
    categories = [t.category for t in dealt]
    assert set(categories[:8]) == {p[0].category for p in POOLS}
    assert len(dealt) == 9


def test_every_topic_carries_its_own_category():
    expected = {
        Category.CS: CS_TOPICS,
        Category.IE: IE_TOPICS,
        Category.AI: AI_TOPICS,
        Category.LITERATURE: LITERATURE_TOPICS,
        Category.HISTORY: HISTORY_TOPICS,
        Category.WORLD: WORLD_TOPICS,
        Category.KOREA: KOREA_TOPICS,
        Category.RESEARCH: RESEARCH_TOPICS,
    }
    for category, pool in expected.items():
        assert {t.category for t in pool} == {category}
