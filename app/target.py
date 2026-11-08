"""The fares of a trip at or below its target price (#847)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.currency import load_rates, to_eur
from app.models import Fare, Itinerary, Leg, Trip


@dataclass(frozen=True)
class TargetFare:
    itinerary_id: int
    fare_id: int
    source: str
    fare_name: str | None
    currency: str
    price: Decimal
    eur: Decimal
    depart_at: datetime | None
    mode_summary: str | None
    depart_offset_min: int | None = None  # the original offset of the first leg: the local time (#448)


def at_target(session: Session, trip: Trip) -> list[TargetFare]:
    """The fares of the shown itineraries whose latest price in EUR is at or below the target, the cheapest first.

    A fare with no rate is not in the list; a trip with no target gives an empty list."""
    if trip.target_price is None:
        return []
    rates = load_rates(session)
    first_offset = select(Leg.depart_offset_min).where(Leg.itinerary_id == Itinerary.id).order_by(Leg.seq).limit(1)
    rows = session.execute(
        select(Fare, Itinerary.depart_at, Itinerary.mode_summary, first_offset.scalar_subquery().label("offset"))
        .join(Itinerary, Fare.itinerary_id == Itinerary.id)
        .where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False), Fare.latest_price.is_not(None))
        .order_by(Fare.id)).all()
    result = []
    for f, d, m, o in rows:
        eur = to_eur(f.latest_price, f.currency, rates)
        if eur is not None and eur <= trip.target_price:
            result.append(TargetFare(f.itinerary_id, f.id, f.source, f.fare_name, f.currency, f.latest_price, eur,
                                     d, m, o))
    return sorted(result, key=lambda t: (t.eur, t.fare_id))
