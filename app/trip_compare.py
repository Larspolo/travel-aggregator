"""The values of one trip on the compare-trips page (#2554): the dates, the best offer, the cheapest and the fastest
offer, the count of offers and the newest capture."""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, subqueryload

from app import departed
from app.currency import by_eur, load_rates, to_eur
from app.models import Capture, Itinerary, Trip
from app.web.pages import _gone, best_for_weights, current_fares, resolve_weights


@dataclass(frozen=True)
class TripValues:
    date_from: date | None
    date_to: date | None
    best: tuple | None  # (itinerary, fare, cost) of best_for_weights(), None when no offer
    cheapest: tuple | None  # (itinerary, fare) with the lowest price in EUR, None when no offer has a rate
    fastest: tuple | None  # (itinerary, fare) with the shortest duration, None when no offer
    count: int  # the visible, not departed offers with a fare
    newest_capture: datetime | None  # the time of the newest capture of the trip


def trip_values(session: Session, trip: Trip, now: datetime | None = None) -> TripValues:
    """The values of `trip` at `now`. A hidden or departed offer does not count (the same rule as the trip page)."""
    now = now or datetime.now(timezone.utc)
    weights, _ = resolve_weights(session, trip, {}, None)
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False),
                                                  departed.not_departed(now))
                          .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    offers = [it for it in its if it.fares]
    gone = _gone(session, its)
    rates = load_rates(session)

    cheapest = None
    fastest = None
    for it in offers:
        fare = by_eur(current_fares(it.fares, gone), rates)[0]  # the cheapest fare of the offer
        eur = to_eur(fare.latest_price, fare.currency, rates)
        if eur is not None:
            key = (eur, it.depart_at)
            if cheapest is None or key < cheapest[0]:
                cheapest = (key, (it, fare))
        key = (it.duration_min, it.depart_at)
        if fastest is None or key < fastest[0]:
            fastest = (key, (it, fare))

    return TripValues(
        date_from=trip.date_from,
        date_to=trip.date_to,
        best=best_for_weights(session, trip, weights, now),
        cheapest=cheapest[1] if cheapest else None,
        fastest=fastest[1] if fastest else None,
        count=len(offers),
        newest_capture=session.scalar(select(func.max(Capture.captured_at)).where(Capture.trip_id == trip.id)),
    )
