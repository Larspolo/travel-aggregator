"""Timetable changes of the booked journeys that did not arrive yet (#2340, epic #2339), for the Upcoming page.

A leg of a booked journey has a change when a newer capture (a later `last_seen_at`) of another itinerary of the same
trip has a leg with the same carrier (`carrier_names`), the same service number and the same local departure day, but
another departure or arrival time. The newest such leg wins.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.carriers import carrier_names
from app.models import Itinerary, Leg


@dataclass(frozen=True)
class Change:
    service_no: str
    old_depart: datetime  # local times, as the Upcoming page shows them
    old_arrive: datetime
    new_depart: datetime
    new_arrive: datetime


def _local(t: datetime, offset_min: int) -> datetime:
    return t.astimezone(timezone(timedelta(minutes=offset_min)))


def _key(leg: Leg) -> tuple:
    return (carrier_names(leg.carrier), leg.service_no.strip(), _local(leg.depart_at, leg.depart_offset_min).date())


def schedule_changes(session: Session, now: datetime) -> dict[int, list[Change]]:
    """The changes per booked itinerary id; an itinerary without a change has no key."""
    booked = list(session.scalars(
        select(Itinerary).where(Itinerary.booked.is_(True), Itinerary.cancelled_at.is_(None),
                                Itinerary.arrive_at >= now)
        .options(selectinload(Itinerary.legs))
    ).all())
    result: dict[int, list[Change]] = {}
    for it in booked:
        legs = [leg for leg in it.legs if leg.service_no and leg.service_no.strip()]
        if not legs:
            continue
        others = session.scalars(
            select(Itinerary).where(Itinerary.trip_id == it.trip_id, Itinerary.id != it.id,
                                    Itinerary.last_seen_at > it.last_seen_at)
            .options(selectinload(Itinerary.legs)).order_by(Itinerary.last_seen_at.desc(), Itinerary.id.desc())
        ).all()
        for leg in legs:
            key = _key(leg)
            for other in others:  # the newest first
                match = next((o for o in other.legs if o.service_no and o.service_no.strip() and _key(o) == key), None)
                if match is None:
                    continue
                if (match.depart_at, match.arrive_at) != (leg.depart_at, leg.arrive_at):
                    result.setdefault(it.id, []).append(Change(
                        leg.service_no, _local(leg.depart_at, leg.depart_offset_min),
                        _local(leg.arrive_at, leg.arrive_offset_min), _local(match.depart_at, match.depart_offset_min),
                        _local(match.arrive_at, match.arrive_offset_min)))
                break
    return result
