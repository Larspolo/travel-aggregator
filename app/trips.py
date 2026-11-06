"""Queries for the trips pages."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Fare, Itinerary, Trip


@dataclass(frozen=True)
class TripRow:
    id: int
    title: str
    origin_text: str | None
    destination_text: str | None
    date_from: date | None
    date_to: date | None
    status: str
    offer_count: int
    best_price: Decimal | None
    best_currency: str | None


def list_trips(session: Session) -> list[TripRow]:
    """All trips with their offer count and lowest fare price, in one SQL statement."""
    stmt = (
        select(
            Trip.id, Trip.title, Trip.origin_text, Trip.destination_text, Trip.date_from, Trip.date_to,
            Trip.status,
            func.count(func.distinct(Itinerary.id)).label("offer_count"),
            func.min(Fare.latest_price).label("best_price"),
            func.min(Fare.currency).label("best_currency"),
        )
        .outerjoin(Itinerary, (Itinerary.trip_id == Trip.id) & Itinerary.hidden.is_(False))
        .outerjoin(Fare, Fare.itinerary_id == Itinerary.id)
        .group_by(Trip.id)
        .order_by(Trip.date_from.asc().nulls_last(), Trip.id)
    )
    return [TripRow(**row._mapping) for row in session.execute(stmt)]
