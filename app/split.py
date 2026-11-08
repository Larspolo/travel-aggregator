"""The best pairs of the two split trips of a trip (#1178): a connection of the first split trip, a self-transfer at
the via place and a connection of the second one, with the sum of their effective costs."""

import heapq
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.ranking import Weights, _amount
from app.risk import self_transfer_extras

MAX_WAIT = timedelta(hours=6)  # the longest wait at the via place


@dataclass(frozen=True)
class Pair:
    first: Any  # the (itinerary, fare, cost) row of the first split trip
    second: Any  # the (itinerary, fare, cost) row of the second split trip
    extras: tuple[tuple[str, Decimal], ...]  # the self-transfer part
    total: Decimal

    @property
    def breakdown(self) -> str:
        """The sum as plain text, e.g. '€40 + €35 + €10 self-transfer = €85'."""
        parts = [_amount(self.first[2].total), _amount(self.second[2].total)]
        parts += [f"{_amount(v)} {label}" for label, v in self.extras if v != 0]
        return f"{' + '.join(parts)} = {_amount(self.total)}"


def split_pairs(first: Sequence[tuple], second: Sequence[tuple], weights: Weights, limit: int = 5) -> list[Pair]:
    """The `limit` best pairs, sorted by the sum and then by the arrival. The rows are the ranked rows of the two
    trip pages (the hard filters of the profile are already applied). A pair needs a wait of at least
    `short_transfer_min` minutes and at most `MAX_WAIT`."""
    extras = self_transfer_extras(SimpleNamespace(self_transfers=1), weights)
    penalty = sum((v for _, v in extras), Decimal("0"))
    minimum = timedelta(minutes=weights.short_transfer_min)
    a_rows = sorted((r for r in first if r[2].total.is_finite()), key=lambda r: r[2].total)
    b_rows = sorted((r for r in second if r[2].total.is_finite()), key=lambda r: r[2].total)
    if not a_rows or not b_rows or limit <= 0:
        return []
    b_min = b_rows[0][2].total
    heap: list = []  # the best pairs so far: (-total, arrival negated as a timestamp, counter, pair)
    count = 0
    for a in a_rows:
        bound = a[2].total + b_min + penalty
        if len(heap) >= limit and bound > -heap[0][0]:
            break
        earliest = a[0].arrive_at + minimum
        latest = a[0].arrive_at + MAX_WAIT
        for b in b_rows:
            total = a[2].total + b[2].total + penalty
            if len(heap) >= limit and total > -heap[0][0]:
                break
            if not earliest <= b[0].depart_at <= latest:
                continue
            key = (-total, -b[0].arrive_at.timestamp(), count)
            count += 1
            item = (*key, Pair(a, b, extras, total))
            if len(heap) < limit:
                heapq.heappush(heap, item)
            elif key > heap[0][:3]:
                heapq.heapreplace(heap, item)
    pairs = [item[3] for item in heap]
    return sorted(pairs, key=lambda p: (p.total, p.second[0].arrive_at))
