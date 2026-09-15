import random

from app.models import Category
from app.topics import (
    HISTORY_TOPICS,
    KOREA_TOPICS,
    LITERATURE_TOPICS,
    RESEARCH_TOPICS,
    TECH_TOPICS,
    TOPICS,
    WORLD_TOPICS,
    pick_topic,
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


def test_topics_span_six_domains():
    pools = (TECH_TOPICS, LITERATURE_TOPICS, HISTORY_TOPICS, WORLD_TOPICS, KOREA_TOPICS, RESEARCH_TOPICS)
    assert set(TOPICS) == set().union(*(set(p) for p in pools))
    assert min(len(p) for p in pools) >= 10
    assert len(set(TEXTS)) == len(TEXTS)


def test_every_topic_carries_its_own_category():
    expected = {
        Category.TECH: TECH_TOPICS,
        Category.LITERATURE: LITERATURE_TOPICS,
        Category.HISTORY: HISTORY_TOPICS,
        Category.WORLD: WORLD_TOPICS,
        Category.KOREA: KOREA_TOPICS,
        Category.RESEARCH: RESEARCH_TOPICS,
    }
    for category, pool in expected.items():
        assert {t.category for t in pool} == {category}
