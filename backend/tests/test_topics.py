import random

from app.topics import HISTORY_TOPICS, LITERATURE_TOPICS, TECH_TOPICS, TOPICS, WORLD_TOPICS, pick_topic


def test_pick_topic_avoids_recent():
    recent = TOPICS[:-1]
    assert pick_topic(recent, rng=random.Random(0)) == TOPICS[-1]


def test_pick_topic_falls_back_when_all_recent():
    assert pick_topic(list(TOPICS), rng=random.Random(0)) in TOPICS


def test_pick_topic_is_random_among_unused():
    picks = {pick_topic([], rng=random.Random(seed)) for seed in range(50)}
    assert len(picks) > 1


def test_topics_span_four_domains():
    pools = (TECH_TOPICS, LITERATURE_TOPICS, HISTORY_TOPICS, WORLD_TOPICS)
    assert set(TOPICS) == set().union(*(set(p) for p in pools))
    assert min(len(p) for p in pools) >= 10
    assert len(set(TOPICS)) == len(TOPICS)
