"""The best effective cost of a trip per day, by the weights of the active profile (#2140)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Fare, FarePrice, Itinerary
from app.ranking import Weights
from app.trend import _day
from app.web.pages import row_cost

# A past day has no "stale" part: the stale part is about the age of a row now, not on that day.
_NO_STALE = datetime.min.replace(tzinfo=UTC)


class _FareOnDay:
    """A fare with the price of one day; it gives all other attributes of the fare."""

    def __init__(self, fare: Fare, price: Decimal, currency: str):
        self._fare, self.latest_price, self.currency = fare, price, currency

    def __getattr__(self, name):
        return getattr(self._fare, name)


def trip_score_trend(session: Session, trip, weights: Weights, places, rates=None, counts=None,
                     fees=None) -> list[tuple[date, Decimal]]:
    """The lowest effective cost (`row_cost()`) of the trip at the end of each day, from its first to its last
    capture. A day with no capture keeps the value of the day before. Each itinerary that is not hidden counts with
    the newest price of each fare at the end of the day; a fare with no price row yet does not count. No row is
    stale on a past day (`stale_before` is the earliest time)."""
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False))
                          .options(selectinload(Itinerary.fares))).all()
    fares = {f.id: (it, f) for it in its for f in it.fares}
    rows = session.execute(
        select(FarePrice.fare_id, FarePrice.price, FarePrice.currency, FarePrice.captured_at)
        .where(FarePrice.fare_id.in_(fares)).order_by(FarePrice.captured_at, FarePrice.id)).all() if fares else []
    if not rows:
        return []
    result: list[tuple[date, Decimal]] = []
    newest: dict[int, tuple[Decimal, str]] = {}  # fare id to its newest price and currency so far
    i, day, last = 0, _day(rows[0].captured_at), _day(rows[-1].captured_at)
    while day <= last:
        while i < len(rows) and _day(rows[i].captured_at) <= day:
            newest[rows[i].fare_id] = (rows[i].price, rows[i].currency)
            i += 1
        by_it: dict[int, list] = {}
        for fare_id, (price, currency) in newest.items():
            it, fare = fares[fare_id]
            by_it.setdefault(it.id, [it]).append(_FareOnDay(fare, price, currency))
        costs = [row_cost(v[0], v[1:], places, weights, _NO_STALE, rates, counts, fees)[1].total
                 for v in by_it.values()]
        result.append((day, min(costs)))
        day += timedelta(days=1)
    return result
