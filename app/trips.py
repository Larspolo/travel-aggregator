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
    return_of_id: int | None = None


def list_trips(session: Session) -> list[TripRow]:
    """All trips with their offer count and lowest fare price, in one SQL statement."""
    stmt = (
        select(
            Trip.id, Trip.title, Trip.origin_text, Trip.destination_text, Trip.date_from, Trip.date_to,
            Trip.status, Trip.return_of_id,
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


def _journey_total(out: TripRow, ret: TripRow) -> str:
    """The sum of the two best prices of a journey (#341); "no total" when one has no price or the currencies differ."""
    if out.best_price is None or ret.best_price is None or out.best_currency != ret.best_currency:
        return "no total"
    return f"{out.best_currency} {out.best_price + ret.best_price}"


def in_journeys(rows: list[TripRow]) -> list[tuple[str, TripRow, str]]:
    """The list lines: each outbound trip, then its return trip (kind "return", the note is the outbound title),
    then the journey total (kind "total", the note is the total). The order of the outbound trips is kept (#341)."""
    returns = {r.return_of_id: r for r in rows if r.return_of_id is not None}
    outbound_ids = {r.id for r in rows}
    lines: list[tuple[str, TripRow, str]] = []
    for r in rows:
        if r.return_of_id is not None and r.return_of_id in outbound_ids:
            continue  # placed under its outbound trip
        lines.append(("trip", r, ""))
        ret = returns.get(r.id)
        if ret is not None:
            lines.append(("return", ret, r.title))
            lines.append(("total", ret, _journey_total(r, ret)))
    return lines
