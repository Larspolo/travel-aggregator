"""The time-of-day extras of an itinerary (#141): a penalty for an early departure or a late arrival."""

from datetime import timedelta
from decimal import Decimal

from app.ranking import Weights


def _local(at, offset_min: int):
    """Give the local wall-clock time of a UTC instant with its stored offset."""
    return (at + timedelta(minutes=offset_min)).time().replace(tzinfo=None)


def time_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the penalty when the first leg departs before the early limit or the last leg arrives after the late limit.

    The local time of the stored offset decides, not UTC. A penalty of 0 adds no part.
    """
    penalty = Decimal(weights.time_window_penalty)
    if penalty == 0 or not itinerary.legs:
        return ()
    first, last = itinerary.legs[0], itinerary.legs[-1]
    extras: list[tuple[str, Decimal]] = []
    if _local(first.depart_at, first.depart_offset_min) < weights.early_limit:
        extras.append(("early departure", penalty))
    if _local(last.arrive_at, last.arrive_offset_min) > weights.late_limit:
        extras.append(("late arrival", penalty))
    return tuple(extras)
