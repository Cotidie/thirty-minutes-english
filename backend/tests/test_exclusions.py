import random

from app.exclusions import Exclusions


def test_thin_keeps_roughly_the_requested_share():
    ex = Exclusions(expressions=tuple(f"e{i}" for i in range(1000)), words=tuple(f"w{i}" for i in range(1000)))
    kept = ex.thin(0.9, random.Random(1))
    assert 850 <= len(kept.expressions) <= 950
    assert 850 <= len(kept.words) <= 950


def test_thin_at_one_keeps_everything_and_at_zero_drops_everything():
    ex = Exclusions(("a", "b"), ("c",))
    assert ex.thin(1.0, random.Random(0)) == ex
    assert not ex.thin(0.0, random.Random(0))
