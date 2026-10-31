import random
from datetime import date

import pytest

from app.models import CATEGORY_LABELS, Category
from app.topics.curated import CURATED
from app.topics.daily import POOL_COUNT
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
    domains = {t.category for t in CURATED_TOPICS}
    dealt = pool_for_day(date(2026, 9, 21), len(domains) + 1, CURATED_TOPICS)
    categories = [t.category for t in dealt]
    assert set(categories[: len(domains)]) == domains
    assert len(dealt) == len(domains) + 1


@pytest.mark.parametrize(
    ("category", "label", "size"), [(Category.ECONOMICS, "Economics", 50), (Category.TRAVEL, "Travel", 70)]
)
def test_a_later_pool_has_its_own_topics_with_a_name_in_the_key(category, label, size):
    pool = CURATED[category]
    others = {text for other, texts in CURATED.items() if other != category for text in texts}
    assert len(pool) == size and len(set(pool)) == size
    assert not others & set(pool)
    assert CATEGORY_LABELS[category] == label
    assert max(map(len, pool)) <= 62  # no longer than the longest chip in the other pools


def test_a_day_has_room_for_every_curated_category():
    assert POOL_COUNT >= len(CURATED)
