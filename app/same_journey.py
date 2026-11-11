"""Join two itineraries of one trip that are the same journey (#2144), and split them again.

`join(session, a, b)` moves the fares of B (with their price rows) to A and sets `B.merged_into_id`; then an ingest
of the fingerprint of B updates A (`app/ingest.py`, `_upsert_one`). B stays as a row with no fare, so that its
fingerprint and its legs stay for the ingest and for `split()`. The caller commits.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fare, Itinerary

# The fields of a booking (#1146, #1685, #1691, #1716): they go together from B to A, and back at a split.
BOOKING = ("booked", "booked_fare_id", "booked_price", "booked_currency", "booked_at", "cancelled_at",
           "refund_price", "travel_day_sent_at", "delay_min", "claim_paid_at", "booking_code")


class JoinError(ValueError):
    """The two rows cannot be joined or split; the text says why."""


def _has_booking(it: Itinerary) -> bool:
    return it.booked or it.cancelled_at is not None


def _move_booking(source: Itinerary, target: Itinerary) -> None:
    for name in BOOKING:
        setattr(target, name, getattr(source, name))
    for name in BOOKING:
        setattr(source, name, False if name == "booked" else None)


def join(session: Session, a: Itinerary, b: Itinerary) -> None:
    """Join B into A. `JoinError` when they are one row, are in two trips, one is joined already, B has rows joined
    into it, both have a booking, or both have a fare of the same source and fare name (the ingest matches a fare by
    itinerary, source and fare name, so two such fares on A would get the same prices).

    A gets the pin of B, the booking of B when A has none, and the note of B when A has none. B keeps its note and
    loses its pin and its booking: the pages and messages that find rows by these flags (pinned, Upcoming, the
    calendar feed, the travel-day message) then show the journey once, on A."""
    if a.id == b.id:
        raise JoinError("a row cannot be joined into itself")
    if a.trip_id != b.trip_id:
        raise JoinError("the rows are in two trips: only rows of one trip can be joined")
    if a.merged_into_id is not None or b.merged_into_id is not None:
        raise JoinError("a row is joined into another row already: split it first")
    if session.scalar(select(Itinerary.id).where(Itinerary.merged_into_id == b.id).limit(1)) is not None:
        raise JoinError("other rows are joined into the second row: join them into the first row one by one")
    if _has_booking(a) and _has_booking(b):
        raise JoinError("both rows have a booking: cancel or remove one booking first")
    own = {(f.source, f.fare_name) for f in a.fares}
    same = sorted({f"{f.source} {f.fare_name or '(no fare name)'}" for f in b.fares if (f.source, f.fare_name) in own})
    if same:
        raise JoinError(f"both rows have the fare {', '.join(same)}: they cannot be joined")
    with session.no_autoflush:  # an autoflush between remove and append deletes the fare (delete-orphan)
        for fare in list(b.fares):
            b.fares.remove(fare)
            fare.moved_from_id = b.id
            a.fares.append(fare)
    a.pinned, b.pinned = a.pinned or b.pinned, False
    if _has_booking(b):
        _move_booking(b, a)
    a.note = a.note or b.note
    a.last_seen_at = max(a.last_seen_at, b.last_seen_at)
    b.merged_into_id = a.id
    session.flush()


def split(session: Session, a: Itinerary, b: Itinerary) -> None:
    """Split B from A: the reverse of `join()`. The fares that came from B (also the fares that an ingest of B
    added after the join) go back to B with all their price rows. The booking goes back to B when its paid fare is
    one of these fares. The pin and the note stay on A: no column records that they came from B.
    `JoinError` when B is not joined into A."""
    if b.merged_into_id != a.id:
        raise JoinError("the second row is not joined into the first row")
    moved = [f for f in a.fares if f.moved_from_id == b.id]
    with session.no_autoflush:  # an autoflush between remove and append deletes the fare (delete-orphan)
        b.fares  # noqa: B018  (load the list before the move)
        for fare in moved:
            a.fares.remove(fare)
            fare.moved_from_id = None
            b.fares.append(fare)
    if a.booked_fare_id is not None and a.booked_fare_id in {f.id for f in moved} and not _has_booking(b):
        _move_booking(a, b)
    b.merged_into_id = None
    session.flush()


def joined_into(session: Session, it: Itinerary) -> Itinerary:
    """The row that `it` is joined into, else `it`."""
    if it.merged_into_id is None:
        return it
    return session.get(Itinerary, it.merged_into_id) or it


def fare_of(it: Itinerary, source: str, fare_name: str | None, origin_id: int | None) -> Fare | None:
    """The fare of `it` with this source and fare name that came from the row `origin_id` (None: the own fares of
    `it`). The ingest uses it so that the offers of A and of a joined B never update the fare of the other row."""
    return next((f for f in it.fares if f.source == source and f.fare_name == fare_name
                 and f.moved_from_id == origin_id), None)
