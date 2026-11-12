"""The days next to the date span of a trip that are cheaper than the cheapest price of the trip (#2524).

The days are the three days before and the three days after the span, from today on. One line per day: the cheapest
source of that day, when its EUR price is less than the cheapest price of the trip. Money is `Decimal`, never `float`.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

NEARBY = 3  # the days before and after the span


@dataclass(frozen=True)
class NearbyDay:
    day: date  # the local day, next to the span
    source: str  # the source of the cheapest price of the day
    price: Decimal  # the price of the day, in its own currency
    currency: str
    price_eur: Decimal  # the price in EUR, rounded to cents
    less_eur: Decimal  # cheapest_eur minus price_eur: always more than 0


def nearby_days(prices: Sequence[Any], date_from: date | None, date_to: date | None, cheapest_eur: Decimal | None,
                today: date, to_eur: Callable[[Decimal, str], Decimal | None]) -> list[NearbyDay]:
    """The days next to the span of the trip that are cheaper than `cheapest_eur`, in date order.

    `prices` are `models.DayPrice` rows; `to_eur` gives the EUR value of an amount (None when the currency has no
    rate, such a day is left out). No `date_from` or no `cheapest_eur`: an empty list.
    """
    if date_from is None or cheapest_eur is None:
        return []
    last = date_to if date_to is not None and date_to >= date_from else date_from
    wanted = {date_from - timedelta(days=i) for i in range(1, NEARBY + 1)}
    wanted |= {last + timedelta(days=i) for i in range(1, NEARBY + 1)}
    wanted = {d for d in wanted if d >= today}

    cheapest: dict[date, NearbyDay] = {}
    for p in prices:
        if p.day not in wanted:
            continue
        eur = to_eur(p.price, p.currency)
        if eur is None or eur >= cheapest_eur:
            continue
        kept = cheapest.get(p.day)
        if kept is None or eur < kept.price_eur:
            cheapest[p.day] = NearbyDay(p.day, p.source, p.price, p.currency, eur, cheapest_eur - eur)
    return [cheapest[d] for d in sorted(cheapest)]


def add_day_span(date_from: date, date_to: date | None, picked: date) -> tuple[date, date | None]:
    """The span of the trip after "Add this day" (#2525): a day before the span moves the first date (an empty last date
    becomes the old first date); a day after the span moves the last date. Only the days next to the span are allowed.
    Raises ValueError for any other day."""
    last = date_to if date_to is not None and date_to >= date_from else date_from
    if picked in {date_from - timedelta(days=i) for i in range(1, NEARBY + 1)}:
        return picked, date_to if date_to is not None else date_from
    if picked in {last + timedelta(days=i) for i in range(1, NEARBY + 1)}:
        return date_from, picked
    raise ValueError(f"{picked.isoformat()} is not next to the span")
