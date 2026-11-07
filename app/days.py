"""The best offer per departure day of a trip (#710): for each day, the row with the best effective cost, the row with
the cheapest price and the count of the offers of that day."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

MAX_DAYS = 31  # the days of the range of the trip (a longer range shows its first 31 days)


@dataclass(frozen=True)
class Day:
    day: str  # the local departure date, YYYY-MM-DD
    best: Any | None  # the (itinerary, fare, cost) row with the lowest cost.total; None for a day with no row
    cheapest: Any | None  # the row with the lowest cost.price; None for a day with no row
    count: int  # the offers of the day, hidden offers excluded


def day_summary(rows: Sequence[tuple], date_from: date | None, date_to: date | None,
                day_of: Callable[[Any], str | None]) -> list[Day]:
    """The days of the range (from `date_from` to `date_to`, or only `date_from`) and each other day that has a row,
    in date order. `rows` are (itinerary, fare, cost) tuples; `day_of` gives an itinerary's day, None to skip it."""
    days: dict[str, list[tuple]] = {}
    if date_from is not None:
        last = date_to if date_to is not None and date_to >= date_from else date_from
        span = min((last - date_from).days + 1, MAX_DAYS)
        for i in range(span):
            days[(date_from + timedelta(days=i)).isoformat()] = []
    for row in rows:
        it = row[0]
        if it.hidden:
            continue  # a hidden offer is in no day (#200)
        key = day_of(it)
        if key is None:
            continue
        days.setdefault(key, []).append(row)
    summary = []
    for key in sorted(days):
        found = days[key]
        best = min(found, key=lambda r: r[2].total) if found else None
        cheapest = min(found, key=lambda r: r[2].price) if found else None
        summary.append(Day(key, best, cheapest, len(found)))
    return summary
