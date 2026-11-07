"""Queries for the trips pages."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.currency import EUR, to_eur
from app.models import CurrencyRate, Fare, Itinerary, Trip


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
    no_rate: bool = False


def list_trips(session: Session) -> list[TripRow]:
    """All trips with their offer count and best offer by its EUR value, in one SQL statement (#386).

    The rates come with the same statement (a join of `currency_rates`), so the page stays one query.
    A fare with no rate does not count; a trip with only such fares shows its lowest price with `no_rate`."""
    stmt = (
        select(
            Trip.id, Trip.title, Trip.origin_text, Trip.destination_text, Trip.date_from, Trip.date_to,
            Trip.status, Trip.return_of_id, Itinerary.id.label("itinerary_id"),
            Fare.latest_price, Fare.currency, CurrencyRate.eur_per_unit,
        )
        .outerjoin(Itinerary, (Itinerary.trip_id == Trip.id) & Itinerary.hidden.is_(False))
        .outerjoin(Fare, (Fare.itinerary_id == Itinerary.id) & Fare.latest_price.is_not(None))
        .outerjoin(CurrencyRate, CurrencyRate.code == Fare.currency)
        .order_by(Trip.date_from.asc().nulls_last(), Trip.id)
    )
    rows = session.execute(stmt).all()
    rates = {r.currency: r.eur_per_unit for r in rows if r.currency is not None and r.eur_per_unit is not None}
    trips: dict[int, dict] = {}
    for r in rows:
        info = trips.setdefault(r.id, {"row": r, "itineraries": set(), "fares": []})
        if r.itinerary_id is not None:
            info["itineraries"].add(r.itinerary_id)
        if r.latest_price is not None:
            info["fares"].append((r.latest_price, r.currency))
    return [_trip_row(info, rates) for info in trips.values()]


def _trip_row(info: dict, rates: dict[str, Decimal]) -> TripRow:
    r = info["row"]
    priced = [(to_eur(price, cur, rates), cur) for price, cur in info["fares"]]
    in_eur = [(eur, cur) for eur, cur in priced if eur is not None]
    best_price: Decimal | None = None
    best_currency: str | None = None
    no_rate = False
    if in_eur:
        best_price, best_currency = min(in_eur, key=lambda pair: pair[0])
        best_currency = EUR
    elif info["fares"]:
        best_price, best_currency = min(info["fares"], key=lambda pair: pair[0])
        no_rate = True
    return TripRow(
        id=r.id, title=r.title, origin_text=r.origin_text, destination_text=r.destination_text,
        date_from=r.date_from, date_to=r.date_to, status=r.status, offer_count=len(info["itineraries"]),
        best_price=best_price, best_currency=best_currency, return_of_id=r.return_of_id, no_rate=no_rate,
    )


def _journey_total(out: TripRow, ret: TripRow) -> str:
    """The sum of the two best offers of a journey in EUR (#341, #386); "no total" when one has no price or no rate."""
    if out.best_price is None or ret.best_price is None or out.no_rate or ret.no_rate:
        return "no total"
    return f"{EUR} {out.best_price + ret.best_price}"


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


def archived_journeys(rows: list[TripRow], archived: bool) -> list[tuple[str, TripRow, str]]:
    """The list lines of the archived trips (`archived` True) or of the other trips (#487).

    A return trip stays with its outbound trip: the status of the outbound trip decides for both."""
    by_id = {r.id: r for r in rows}

    def group_archived(r: TripRow) -> bool:
        out = by_id.get(r.return_of_id) if r.return_of_id is not None else None
        return (out or r).status == "archived"

    return in_journeys([r for r in rows if group_archived(r) == archived])
