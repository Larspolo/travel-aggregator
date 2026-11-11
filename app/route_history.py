"""The older trips on the same route as a trip, with their cheapest seen price and their paid price (#1521)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.currency import load_rates, to_eur
from app.models import Capture, Fare, FarePrice, Itinerary, Trip
from app.parsers import group_price
from app.ranking import per_traveler
from app.place_names import aliases
from app.tripmatch import _groups, _phrase

LIMIT = 5
CENT = Decimal("0.01")


@dataclass(frozen=True)
class RouteTrip:
    trip_id: int
    title: str
    month: date  # the first day of the month of the trip
    cheapest_eur: Decimal | None
    paid_eur: Decimal | None


def _start(trip: Trip) -> date:
    return trip.date_from or trip.created_at.date()


def _same_place(a: str | None, b: str | None, aliases=None) -> bool:
    """Two texts name the same place: their folded phrases are equal or they share an ALIASES group."""
    if not a or not b:
        return False
    return _phrase(a) == _phrase(b) or bool(_groups(a, aliases) & _groups(b, aliases))


def _cheapest(session: Session, trip_id: int, rates) -> Decimal | None:
    """The lowest EUR value per traveler of all prices of the visible itineraries; a price with no rate does not count."""
    rows = session.execute(
        select(FarePrice.price, FarePrice.currency, Fare.source, Capture.travelers)
        .join(Fare, FarePrice.fare_id == Fare.id)
        .join(Itinerary, Fare.itinerary_id == Itinerary.id)
        .outerjoin(Capture, FarePrice.capture_id == Capture.id)
        .where(Itinerary.trip_id == trip_id, Itinerary.hidden.is_(False))).all()
    values = []
    for price, currency, source, travelers in rows:
        eur = to_eur(price, currency, rates)
        if eur is not None:
            values.append(per_traveler(eur, travelers if group_price(source) else None))
    return min(values).quantize(CENT) if values else None


def _paid(session: Session, trip: Trip, rates) -> Decimal | None:
    """The booked price of the booked itinerary in EUR, per traveler of the trip."""
    it = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.booked.is_(True),
                                                 Itinerary.booked_price.is_not(None))).first()
    if it is None:
        return None
    eur = to_eur(it.booked_price, it.booked_currency or "EUR", rates)
    return None if eur is None else per_traveler(eur, trip.travelers).quantize(CENT)


def route_history(session: Session, trip: Trip) -> list[RouteTrip]:
    """The older trips (not split parts) with the same origin and destination, newest first, at most LIMIT."""
    start = _start(trip)
    names = aliases(session)
    older = [t for t in session.scalars(select(Trip).where(Trip.id != trip.id, Trip.split_of_id.is_(None)))
             if _start(t) < start and _same_place(t.origin_text, trip.origin_text, names)
             and _same_place(t.destination_text, trip.destination_text, names)]
    older.sort(key=lambda t: (_start(t), t.id), reverse=True)
    rates = load_rates(session)
    return [RouteTrip(t.id, t.title, _start(t).replace(day=1), _cheapest(session, t.id, rates), _paid(session, t, rates))
            for t in older[:LIMIT]]
