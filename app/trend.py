"""The cheapest price of a trip per day, for the price trend chart (#850)."""

from datetime import UTC, date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.currency import load_rates, to_eur
from app.models import Fare, FarePrice, Itinerary


def _day(captured_at) -> date:
    return captured_at.astimezone(UTC).date()


def trip_trend(session: Session, trip_id: int) -> list[tuple[date, Decimal]]:
    """The lowest EUR value of the trip at the end of each day, from its first to its last capture (EUR, one
    entry per day). A day with no capture keeps the value of the day before. A price with no rate does not count."""
    rates = load_rates(session)
    rows = session.execute(
        select(FarePrice.fare_id, FarePrice.price, FarePrice.currency, FarePrice.captured_at)
        .join(Fare, FarePrice.fare_id == Fare.id)
        .join(Itinerary, Fare.itinerary_id == Itinerary.id)
        .where(Itinerary.trip_id == trip_id, Itinerary.hidden.is_(False))
        .order_by(FarePrice.captured_at, FarePrice.id)).all()
    if not rows:
        return []
    result: list[tuple[date, Decimal]] = []
    newest: dict[int, Decimal] = {}  # fare id to the EUR value of its newest rated price so far
    i = 0
    day = _day(rows[0].captured_at)
    last = _day(rows[-1].captured_at)
    while day <= last:
        while i < len(rows) and _day(rows[i].captured_at) <= day:
            fare_id, price, currency, _ = rows[i]
            eur = to_eur(price, currency, rates)
            if eur is not None:
                newest[fare_id] = eur
            i += 1
        if newest:
            result.append((day, min(newest.values())))
        day += timedelta(days=1)
    return result
