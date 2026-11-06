"""The price drops of the pinned offers of a trip since the last view of its page (#355)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Fare, Itinerary


@dataclass(frozen=True)
class Drop:
    itinerary_id: int
    fare_id: int
    source: str
    fare_name: str | None
    currency: str
    seen_price: Decimal
    latest_price: Decimal
    amount: Decimal
    depart_at: datetime | None
    mode_summary: str | None


def trip_drops(session: Session, trip_id: int) -> list[Drop]:
    """The fares of the pinned, shown itineraries that are cheaper than at the last view, the largest drop first."""
    amount = Fare.seen_price - Fare.latest_price
    rows = session.execute(
        select(Fare, Itinerary.depart_at, Itinerary.mode_summary, amount.label("amount"))
        .join(Itinerary, Fare.itinerary_id == Itinerary.id)
        .where(Itinerary.trip_id == trip_id, Itinerary.pinned, Itinerary.hidden.is_(False),
               Fare.seen_price.is_not(None), Fare.latest_price < Fare.seen_price)
        .order_by(amount.desc(), Fare.id)).all()
    return [Drop(f.itinerary_id, f.id, f.source, f.fare_name, f.currency, f.seen_price, f.latest_price, a, d, m)
            for f, d, m, a in rows]


def mark_seen(session: Session, trip_id: int) -> None:
    """Store the current price of each fare of the trip as the seen price."""
    ids = select(Itinerary.id).where(Itinerary.trip_id == trip_id)
    session.execute(update(Fare).where(Fare.itinerary_id.in_(ids),
                                       Fare.seen_price.is_distinct_from(Fare.latest_price))
                    .values(seen_price=Fare.latest_price).execution_options(synchronize_session=False))
