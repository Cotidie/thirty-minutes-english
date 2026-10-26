import random
from datetime import date

from app.topics.pool import pick_topic, pool_for_day
from tests.conftest import CURATED_TOPICS

TEXTS = [t.text for t in CURATED_TOPICS]


def test_pick_topic_avoids_recent():
    assert pick_topic(TEXTS[:-1], TEXTS, rng=random.Random(0)) == TEXTS[-1]


def test_pick_topic_falls_back_when_all_recent():
    assert pick_topic(TEXTS, TEXTS, rng=random.Random(0)) in TEXTS


def test_pick_topic_is_random_among_unused():
    picks = {pick_topic([], TEXTS, rng=random.Random(seed)) for seed in range(50)}
    assert len(picks) > 1


def test_a_day_shows_every_domain_before_repeating_one():
    dealt = pool_for_day(date(2026, 9, 21), 9, CURATED_TOPICS)
    categories = [t.category for t in dealt]
    assert set(categories[:8]) == {t.category for t in CURATED_TOPICS}
    assert len(dealt) == 9
