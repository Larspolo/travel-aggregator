"""The best pairs of the split trips (#1178)."""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights, effective_cost
from app.split import split_pairs

T0 = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def row(depart_min, duration_min, price, weights=Weights()):
    dep = T0 + timedelta(minutes=depart_min)
    it = SimpleNamespace(depart_at=dep, arrive_at=dep + timedelta(minutes=duration_min))
    return (it, None, effective_cost(Decimal(price), duration_min, 0, weights))


def test_wait_limits():
    w = Weights(short_transfer_min=10)
    a = row(0, 60, "40", w)  # arrives at +60
    exact = row(70, 60, "35", w)
    short = row(69, 60, "1", w)
    long_ = row(60 + 361, 60, "1", w)
    pairs = split_pairs([a], [exact, short, long_], w)
    assert [p.second for p in pairs] == [exact]


def test_sum_and_breakdown():
    w = Weights(hour_markup=Decimal("0"), self_transfer_penalty=Decimal("10"))
    pairs = split_pairs([row(0, 60, "40", w)], [row(90, 60, "35", w)], w)
    assert pairs[0].total == Decimal("85")
    assert pairs[0].breakdown == "€40 + €35 + €10 self-transfer = €85"


def test_hour_value_changes_order():
    def best(w):
        a = row(0, 60, "40", w)
        slow = row(90, 300, "20", w)
        fast = row(90, 60, "40", w)
        return split_pairs([a], [slow, fast], w)[0].second[0].arrive_at
    assert best(Weights(hour_markup=Decimal("0"))) != best(Weights(hour_markup=Decimal("30")))


def test_speed():
    first = [row(i % 600, 60, str(30 + i % 97)) for i in range(1000)]
    second = [row(120 + i % 600, 60, str(30 + i % 89)) for i in range(1000)]
    start = time.perf_counter()
    pairs = split_pairs(first, second, Weights())
    assert time.perf_counter() - start < 0.5
    assert len(pairs) == 5
    assert pairs == sorted(pairs, key=lambda p: (p.total, p.second[0].arrive_at))
