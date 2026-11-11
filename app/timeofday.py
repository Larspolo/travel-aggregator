"""The time-of-day extras of an itinerary (#141): a penalty for an early departure or a late arrival."""

from datetime import datetime, timedelta
from decimal import Decimal

from app.ranking import Weights


def _local(at, offset_min: int):
    """Give the local wall-clock time of a UTC instant with its stored offset."""
    return (at + timedelta(minutes=offset_min)).time().replace(tzinfo=None)


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def weekday_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the markup of the local weekday of the first departure (#2136). A markup of 0 adds no part."""
    if not itinerary.legs:
        return ()
    first = itinerary.legs[0]
    day = (first.depart_at + timedelta(minutes=first.depart_offset_min)).isoweekday()
    markup = Decimal(getattr(weights, f"weekday{day}_markup"))
    return ((WEEKDAYS[day - 1], markup),) if markup != 0 else ()


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


def _night_minutes(start: datetime, end: datetime, weights: Weights) -> int:
    """Give the minutes of the local span start..end inside the night windows. A window may cross midnight."""
    total = timedelta()
    day = start.date() - timedelta(days=1)
    while datetime.combine(day, weights.night_start) < end:
        w_start = datetime.combine(day, weights.night_start)
        w_end = datetime.combine(day + timedelta(days=weights.night_end <= weights.night_start), weights.night_end)
        overlap = min(end, w_end) - max(start, w_start)
        if overlap > timedelta():
            total += overlap
        day += timedelta(days=1)
    return int(total.total_seconds() // 60)


BERTH_LABELS = {"seat": "night in a seat", "couchette": "night in a couchette", "sleeper": "night in a sleeper"}


def night_extras(itinerary, weights: Weights, fare=None) -> tuple[tuple[str, Decimal], ...]:
    """Add the night adjustment when the local time span covers at least night_min minutes of the night window.

    A fare whose berth has a value in the weights (#1808) gets that value as "night in a <berth>"; else
    "night travel" with night_adjust.

    The span starts at the local departure of the first leg and ends at the local arrival of the last leg.
    A negative amount is a bonus. An amount of 0 adds no part.
    """
    berth = getattr(fare, "berth", None)
    value = getattr(weights, f"night_{berth}_adjust", None) if berth in BERTH_LABELS else None
    label = BERTH_LABELS[berth] if value is not None else "night travel"
    amount = Decimal(weights.night_adjust if value is None else value)
    if amount == 0 or not itinerary.legs:
        return ()
    first, last = itinerary.legs[0], itinerary.legs[-1]
    start = (first.depart_at + timedelta(minutes=first.depart_offset_min)).replace(tzinfo=None)
    end = (last.arrive_at + timedelta(minutes=last.arrive_offset_min)).replace(tzinfo=None)
    if _night_minutes(start, end, weights) >= weights.night_min:
        return ((label, amount),)
    return ()


def night_time_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the part "night hours": the night minutes × (night_hour_markup − hour_markup) / 60 (#143).

    The base time part does not change. The amount may be negative. An amount of 0 adds no part.
    """
    if weights.night_hour_markup is None or not itinerary.legs:
        return ()
    diff = Decimal(weights.night_hour_markup) - Decimal(weights.hour_markup)
    if diff == 0:
        return ()
    first, last = itinerary.legs[0], itinerary.legs[-1]
    start = (first.depart_at + timedelta(minutes=first.depart_offset_min)).replace(tzinfo=None)
    end = (last.arrive_at + timedelta(minutes=last.arrive_offset_min)).replace(tzinfo=None)
    minutes = _night_minutes(start, end, weights)
    if minutes == 0:
        return ()
    return (("night hours", Decimal(minutes) * diff / 60),)


def overnight_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the hotel cost for each transfer with at least overnight_min night minutes (#1256).

    The transfer starts at the arrival of leg i and ends at the departure of leg i+1, in the local time of the
    transfer place. A cost of 0 adds no part.
    """
    cost = Decimal(weights.overnight_cost)
    if cost == 0:
        return ()
    extras: list[tuple[str, Decimal]] = []
    for a, b in zip(itinerary.legs, itinerary.legs[1:]):
        start = (a.arrive_at + timedelta(minutes=a.arrive_offset_min)).replace(tzinfo=None)
        end = (b.depart_at + timedelta(minutes=a.arrive_offset_min)).replace(tzinfo=None)
        if _night_minutes(start, end, weights) >= weights.overnight_min:
            extras.append((f"overnight stop in {a.to_name}", cost))
    return tuple(extras)


def arrive_by_extras(itinerary, arrive_by, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the cost of the wait from the local arrival of the last leg to `arrive_by` on the same local date (#1295).

    No part when the markup is 0, the trip has no `arrive_by`, or the offer arrives at or after the time.
    """
    markup = Decimal(weights.wait_hour_markup)
    if markup == 0 or arrive_by is None or not itinerary.legs:
        return ()
    last = itinerary.legs[-1]
    arrival = (last.arrive_at + timedelta(minutes=last.arrive_offset_min)).replace(tzinfo=None)
    target = datetime.combine(arrival.date(), arrive_by.replace(tzinfo=None))
    minutes = int((target - arrival).total_seconds() // 60)
    if minutes <= 0:
        return ()
    cost = (Decimal(minutes) / 60 * markup).quantize(Decimal("0.01"))
    hours, rest = divmod(minutes, 60)
    span = " ".join(p for p in (f"{hours} h" if hours else "", f"{rest} min" if rest else "") if p)
    return ((f"wait {span} before {arrive_by.strftime('%H:%M')}", cost),)


def leave_after_extras(itinerary, leave_after, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the cost of the wait from the local departure of the first leg to `leave_after` on the same local date (#2022).

    No part when the markup is 0, the trip has no `leave_after`, the itinerary has no legs, or the offer departs at or
    after the time.
    """
    markup = Decimal(weights.leave_hour_markup)
    if markup == 0 or leave_after is None or not itinerary.legs:
        return ()
    first = itinerary.legs[0]
    departure = (first.depart_at + timedelta(minutes=first.depart_offset_min)).replace(tzinfo=None)
    target = datetime.combine(departure.date(), leave_after.replace(tzinfo=None))
    minutes = int((target - departure).total_seconds() // 60)
    if minutes <= 0:
        return ()
    cost = (Decimal(minutes) / 60 * markup).quantize(Decimal("0.01"))
    hours, rest = divmod(minutes, 60)
    span = " ".join(p for p in (f"{hours} h" if hours else "", f"{rest} min" if rest else "") if p)
    return ((f"leave {span} before {leave_after.strftime('%H:%M')}", cost),)
