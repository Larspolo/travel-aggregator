"""What each capture changed on its trip: the itineraries it showed first, and the fares whose price went lower or
higher than the row before (epic #2327, #2328). A fixed number of statements for any number of captures."""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fare, FarePrice


@dataclass
class Changes:
    new: set[int] = field(default_factory=set)  # itinerary ids whose first price row is from the capture
    lower: set[int] = field(default_factory=set)  # itinerary ids with a fare that is lower than its row before
    higher: set[int] = field(default_factory=set)  # itinerary ids with a fare that is higher than its row before


def capture_changes(session: Session, capture_ids) -> dict[int, Changes]:
    """The key is Capture.id; every given id has an entry (empty when nothing changed). 1 statement."""
    capture_ids = list(capture_ids)
    result = {cid: Changes() for cid in capture_ids}
    if not capture_ids:
        return result
    touched = select(Fare.itinerary_id).join(FarePrice, FarePrice.fare_id == Fare.id).where(
        FarePrice.capture_id.in_(capture_ids))
    rows = session.execute(
        select(FarePrice.id, FarePrice.capture_id, FarePrice.fare_id, Fare.itinerary_id, FarePrice.price,
               FarePrice.currency, FarePrice.captured_at)
        .join(Fare, Fare.id == FarePrice.fare_id)
        .where(Fare.itinerary_id.in_(touched))
    ).all()
    by_fare = defaultdict(list)
    first_row = {}  # itinerary id -> (captured_at, id, capture_id) of its first price row
    for row_id, capture_id, fare_id, itinerary_id, price, currency, captured_at in rows:
        by_fare[fare_id].append((captured_at, row_id, capture_id, itinerary_id, price, currency))
        key = (captured_at, row_id)
        if itinerary_id not in first_row or key < first_row[itinerary_id][:2]:
            first_row[itinerary_id] = (captured_at, row_id, capture_id)
    for itinerary_id, (_, _, capture_id) in first_row.items():
        if capture_id in result:
            result[capture_id].new.add(itinerary_id)
    for history in by_fare.values():
        history.sort(key=lambda r: (r[0], r[1]))
        for before, after in zip(history, history[1:]):
            if after[2] not in result or before[5] != after[5]:  # another currency: no count
                continue
            if after[4] < before[4]:
                result[after[2]].lower.add(after[3])
            elif after[4] > before[4]:
                result[after[2]].higher.add(after[3])
    return result
