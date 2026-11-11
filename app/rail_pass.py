"""Does a rail pass cover an itinerary, and how many travel days does it cost (epic #2263).

The functions are pure: they take an itinerary and a rail pass (any object with `name`, `first_day`, `last_day`,
`day_cost` and `carriers`), and they need no database. The carrier rule is the one of `carrier_extras()` in
`app/risk.py` (#2249): a leg has the names of `carrier_names()` and the parts of its raw carrier text, without case
and outer spaces."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.carriers import SEPARATOR, carrier_names


def _local_date(instant: datetime, offset_min: int) -> date:
    """The date on the clock of the place: the UTC instant plus the offset of the place (in minutes)."""
    return (instant.astimezone(timezone.utc) + timedelta(minutes=offset_min)).date()


def _carrier_keys(raw: str | None) -> set[str]:
    """The names of a raw carrier text that a rail pass can match: the table names and the parts, casefolded."""
    keys = {name.casefold() for name in carrier_names(raw)}
    keys |= {part.strip().casefold() for part in (raw or "").split(SEPARATOR) if part.strip()}
    return keys


def _leg_covered(leg, rail_pass, carriers: list[str]) -> bool:
    if leg.mode != "train":
        return False
    dates = (
        _local_date(leg.depart_at, leg.depart_offset_min),
        _local_date(leg.arrive_at, leg.arrive_offset_min),
    )
    if not all(rail_pass.first_day <= day <= rail_pass.last_day for day in dates):
        return False
    if not carriers:
        return True
    keys = _carrier_keys(leg.carrier)
    return any(name.casefold() in keys for name in carriers)


def pass_days(itinerary, rail_pass) -> int | None:
    """The travel days that the pass costs for the itinerary, or None when the pass does not cover it (or the
    itinerary has no legs). A travel day is a day from the local date of the first departure to the local date of
    the last arrival, both days counted."""
    legs = list(itinerary.legs)
    if not legs:
        return None
    carriers = [name.casefold() for name in carrier_names(rail_pass.carriers)] if rail_pass.carriers else []
    if not all(_leg_covered(leg, rail_pass, carriers) for leg in legs):
        return None
    first_departure = min(_local_date(leg.depart_at, leg.depart_offset_min) for leg in legs)
    last_arrival = max(_local_date(leg.arrive_at, leg.arrive_offset_min) for leg in legs)
    return (last_arrival - first_departure).days + 1


def pass_cost(itinerary, rail_pass) -> Decimal | None:
    """The day cost of the pass times the travel days, or None when the pass does not cover the itinerary."""
    days = pass_days(itinerary, rail_pass)
    if days is None:
        return None
    return rail_pass.day_cost * days
