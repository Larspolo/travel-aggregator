"""Queries for the trips pages."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app import departed
from app.currency import EUR, to_eur
from app.gone import gone_fares
from app.suspect import suspect_fares
from app.models import CurrencyRate, Fare, Itinerary, Trip


def alt_places(text: str | None) -> list[str]:
    """The places of a comma-separated text of other origins or destinations (#1422), stripped, with no blank one."""
    return [p.strip() for p in (text or "").split(",") if p.strip()]


def route_text(trip: Trip) -> str | None:
    """The route of a trip with its other places (#1422): "Amsterdam → Zürich or Basel"; None with no place."""
    if not (trip.origin_text or trip.destination_text):
        return None
    origin = " or ".join([trip.origin_text or "?", *alt_places(trip.origin_alt_text)])
    destination = " or ".join([trip.destination_text or "?", *alt_places(trip.destination_alt_text)])
    return f"{origin} → {destination}"


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
    at_target: bool = False  # the best EUR price is at or below the target price (#847)
    shared: bool = False  # the trip has an active share link (#905)
    split_of_id: int | None = None  # the trip that this trip is a part of (#1177)
    notes: str | None = None  # not shown on the list; only searched (#1220)


def list_trips(session: Session) -> list[TripRow]:
    """All trips with their offer count and best offer by its EUR value: 1 SQL statement (#386) and the 2 of
    `gone_fares` (#1387) and the 2 of `suspect_fares` (#1606).

    The rates come with the same statement (a join of `currency_rates`), so the page stays one query.
    A fare with no rate does not count; a trip with only such fares shows its lowest price with `no_rate`."""
    departed_now = departed.clock()  # a departed offer counts for neither the count nor the best offer (#1393)
    stmt = (
        select(
            Trip.id, Trip.title, Trip.origin_text, Trip.destination_text, Trip.date_from, Trip.date_to,
            Trip.status, Trip.return_of_id, Trip.split_of_id, Trip.target_price, Trip.share_hash, Trip.notes,
            Itinerary.id.label("itinerary_id"),
            Fare.id.label("fare_id"), Fare.latest_price, Fare.currency, CurrencyRate.eur_per_unit,
        )
        .outerjoin(Itinerary, (Itinerary.trip_id == Trip.id) & Itinerary.hidden.is_(False)
                    & departed.not_departed(departed_now))
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
            info["fares"].append((r.latest_price, r.currency, r.fare_id))
    gone = set(gone_fares(session, trips)) | set(suspect_fares(session, trips))  # suspect as gone (#1606)
    for info in trips.values():  # a gone fare counts only when the trip has no current fare (#1387)
        current = [f for f in info["fares"] if f[2] not in gone]
        info["fares"] = [f[:2] for f in (current or info["fares"])]
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
        at_target=bool(in_eur) and r.target_price is not None and best_price <= r.target_price,
        shared=r.share_hash is not None, split_of_id=r.split_of_id, notes=r.notes,
    )


def _journey_total(*rows: TripRow) -> str:
    """The sum of the best offers of the trips of a journey in EUR (#341, #386, #561); "no total" when one trip has
    no price or no rate."""
    if any(r.best_price is None or r.no_rate for r in rows):
        return "no total"
    return f"{EUR} {sum(r.best_price for r in rows)}"


def _first_of(r: TripRow, by_id: dict[int, TripRow]) -> TripRow:
    """The first trip of the chain of return_of_id in these rows (a cycle stops the walk)."""
    seen = {r.id}
    while r.return_of_id in by_id and r.return_of_id not in seen:
        r = by_id[r.return_of_id]
        seen.add(r.id)
    return r


def _via(split: TripRow, trip: TripRow) -> str:
    """The place of a split trip (#1180): its destination when it starts where its trip starts, else its origin."""
    return (split.destination_text if split.origin_text == trip.origin_text else split.origin_text) or "?"


def in_journeys(rows: list[TripRow]) -> list[tuple[str, TripRow, str]]:
    """The list lines: each first trip, then the later trips of its chain in sequence, then the journey total (kind
    "total", the note is the total). A chain of 2 has the kind "return" for its second trip, a longer chain the kind
    "next"; the note is the title of the previous trip. The order of the first trips is kept (#341, #561).
    The split trips of a trip follow it (kind "split", the note is the place, #1180); they add nothing to a total."""
    by_id = {r.id: r for r in rows}
    splits: dict[int, list[TripRow]] = {}
    for r in rows:
        if r.split_of_id in by_id:
            splits.setdefault(r.split_of_id, []).append(r)
    after = {r.return_of_id: r for r in rows if r.return_of_id is not None}
    lines: list[tuple[str, TripRow, str]] = []

    def add(kind: str, t: TripRow, note: str) -> None:
        lines.append((kind, t, note))
        lines.extend(("split", s, _via(s, t)) for s in sorted(splits.get(t.id, []), key=lambda s: s.id))

    for r in rows:
        if r.split_of_id in by_id:
            continue  # placed under its trip
        if r.return_of_id is not None and r.return_of_id in by_id and _first_of(r, by_id) is not r:
            continue  # placed under the first trip of its chain
        journey = [r]
        while (nxt := after.get(journey[-1].id)) is not None and nxt not in journey:
            journey.append(nxt)
        add("trip", r, "")
        if len(journey) > 1:
            kind = "return" if len(journey) == 2 else "next"
            for prev, t in zip(journey, journey[1:]):
                add(kind, t, prev.title)
            lines.append(("total", journey[-1], _journey_total(*journey)))
    return lines


def archived_journeys(rows: list[TripRow], archived: bool) -> list[tuple[str, TripRow, str]]:
    """The list lines of the archived trips (`archived` True) or of the other trips (#487).

    The trips of a journey stay together: the status of the first trip of the chain decides for all (#561)."""
    by_id = {r.id: r for r in rows}

    def first(r: TripRow) -> TripRow:  # a split trip goes with its trip (#1180)
        return _first_of(by_id.get(r.split_of_id, r), by_id)
    return in_journeys([r for r in rows if (first(r).status == "archived") == archived])


def find_journeys(rows: list[TripRow], text: str, archived: bool) -> list[tuple[str, TripRow, str]]:
    """The lines of `archived_journeys()` of the journeys with a trip that contains `text` (#1220): in the title,
    origin, destination or note, with no case and no diacritics. A journey shows whole; a blank text keeps all."""
    from app.tripmatch import fold

    lines = archived_journeys(rows, archived)
    needle = fold(text.strip())
    if not needle:
        return lines
    groups: list[list[tuple[str, TripRow, str]]] = []
    for line in lines:
        if line[0] == "trip" or not groups:
            groups.append([])
        groups[-1].append(line)

    def hit(t: TripRow) -> bool:
        return any(needle in fold(v) for v in (t.title, t.origin_text, t.destination_text, t.notes) if v)
    return [line for g in groups if any(kind != "total" and hit(t) for kind, t, _ in g) for line in g]


def chain(trip: Trip) -> list[Trip]:
    """The trips of one journey in order (#560): back along return_of to the first trip, then forward along
    return_trip to the last. A trip that is already in the chain ends the walk (no cycle can hang the page)."""
    first, back = trip, {trip.id}
    while first.return_of is not None and first.return_of.id not in back:
        first = first.return_of
        back.add(first.id)
    journey = [first]
    while (nxt := _linked_after(journey[-1])) is not None and nxt.id not in {t.id for t in journey}:
        journey.append(nxt)
    return journey


def _linked_after(trip: Trip) -> Trip | None:
    """The trip that has this trip as return_of (the query, not the relationship: its join is not one-to-one)."""
    return object_session(trip).scalar(select(Trip).where(Trip.return_of_id == trip.id))
