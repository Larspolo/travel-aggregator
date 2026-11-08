"""The best offer per departure day of a trip (#710): for each day, the row with the best effective cost, the row with
the cheapest price and the count of the offers of that day."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

MAX_DAYS = 31  # the days of the range of the trip (a longer range shows its first 31 days)


@dataclass(frozen=True)
class Day:
    day: str  # the local departure date, YYYY-MM-DD
    best: Any | None  # the (itinerary, fare, cost) row with the lowest cost.total; None for a day with no row
    cheapest: Any | None  # the row with the lowest cost.price; None for a day with no row
    count: int  # the offers of the day, hidden offers excluded
    day_price: Any | None = None  # a stored day price (#1198) of a day with no row: an estimate, not a row


def with_day_prices(days: list[Day], prices: Sequence[Any]) -> list[Day]:
    """Add the cheapest stored day price (`models.DayPrice`, #1197) to each day with no row (#1198). A day with rows
    does not change."""
    cheapest: dict[str, Any] = {}
    for p in prices:
        key = p.day.isoformat()
        if key not in cheapest or p.price < cheapest[key].price:
            cheapest[key] = p
    return [replace(d, day_price=cheapest.get(d.day)) if d.best is None and d.day in cheapest else d for d in days]


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


RETURN_MAX_DAYS = 14  # the outbound days and the return days of a grid (a longer list shows its first 14 days)


@dataclass(frozen=True)
class Cell:
    outbound: str  # the outbound day, YYYY-MM-DD
    back: str  # the return day, YYYY-MM-DD
    total: Decimal | None  # the sum of the two best totals; None when a day has no row or the return day is before


@dataclass(frozen=True)
class Grid:
    outbound: list[str]  # the outbound days, in date order
    back: list[str]  # the return days, in date order
    cells: list[Cell]  # one cell per pair, outbound day first
    best: Cell | None  # the cell with the lowest finite sum; None when no cell has a finite sum


def return_grid(outbound: Sequence[Day], back: Sequence[Day]) -> Grid:
    """The grid of a round trip (#1107): for each outbound day and each return day, the sum of the best totals of
    the two trips. Both lists are the days of `day_summary()`; each keeps its first 14 days."""
    out_days = list(outbound[:RETURN_MAX_DAYS])
    back_days = list(back[:RETURN_MAX_DAYS])
    cells = []
    for o in out_days:
        for b in back_days:
            total = None
            if o.best is not None and b.best is not None and b.day >= o.day:
                total = o.best[2].total + b.best[2].total
            cells.append(Cell(o.day, b.day, total))
    finite = [c for c in cells if c.total is not None and c.total.is_finite()]
    best = min(finite, key=lambda c: c.total) if finite else None
    return Grid([d.day for d in out_days], [d.day for d in back_days], cells, best)
