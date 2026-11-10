"""The lowest captured price per step of days before the departure, for the trips of one route (#1915)."""

from dataclasses import dataclass
from datetime import UTC
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.currency import load_rates, to_eur
from app.models import Capture, Fare, FarePrice, Itinerary
from app.parsers import group_price
from app.ranking import per_traveler

STEPS = ((0, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, None))  # days before the departure; None: no last day
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Step:
    first_day: int
    last_day: int | None
    lowest_eur: Decimal  # per traveler


def _step(days: int) -> tuple[int, int | None] | None:
    return next(((a, b) for a, b in STEPS if days >= a and (b is None or days <= b)), None)


def book_timing(session: Session, trip_ids: list[int]) -> list[Step]:
    """The steps with a capture, in the order of STEPS. Days: the UTC date of the departure less the UTC date of the
    capture. A capture after the departure, a hidden itinerary and a price with no currency rate do not count."""
    if not trip_ids:
        return []
    rows = session.execute(
        select(FarePrice.price, FarePrice.currency, FarePrice.captured_at, Itinerary.depart_at, Fare.source,
               Capture.travelers)
        .join(Fare, FarePrice.fare_id == Fare.id)
        .join(Itinerary, Fare.itinerary_id == Itinerary.id)
        .outerjoin(Capture, FarePrice.capture_id == Capture.id)
        .where(Itinerary.trip_id.in_(trip_ids), Itinerary.hidden.is_(False))).all()
    rates = load_rates(session)
    lowest: dict[tuple[int, int | None], Decimal] = {}
    for price, currency, captured_at, depart_at, source, travelers in rows:
        step = _step((depart_at.astimezone(UTC).date() - captured_at.astimezone(UTC).date()).days)
        eur = to_eur(price, currency, rates)
        if step is None or eur is None:
            continue
        value = per_traveler(eur, travelers if group_price(source) else None)
        if step not in lowest or value < lowest[step]:
            lowest[step] = value
    return [Step(a, b, lowest[(a, b)].quantize(CENT)) for a, b in STEPS if (a, b) in lowest]
