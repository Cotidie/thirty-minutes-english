import random
from datetime import date

from app.models import CATEGORY_LABELS, Category
from app.topics.curated import CURATED
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


def test_economics_has_about_fifty_topics_of_its_own_with_a_name_in_the_key():
    economics = CURATED[Category.ECONOMICS]
    others = {text for category, texts in CURATED.items() if category != Category.ECONOMICS for text in texts}
    assert len(economics) == 50 and len(set(economics)) == 50
    assert not others & set(economics)
    assert CATEGORY_LABELS[Category.ECONOMICS] == "Economics"
    assert max(map(len, economics)) <= 62  # no longer than the longest chip in the other pools
