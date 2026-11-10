"""The hour values at which each booking was the best offer of its trip (epic #1708).

Pure functions: the totals come from `row_cost()` at the hour value `h` and at `h + 1`,
as in `tradeoff_lines()` of `app/web/pages.py`. Reading the bookings is #1710.
"""

from decimal import Decimal

from app.tradeoff import break_even

Totals = tuple[Decimal, Decimal]  # the total at the hour value h and at h + 1
Interval = tuple[Decimal | None, Decimal | None]  # (low, high): None is an end with no limit

_LOW, _HIGH = Decimal("-Infinity"), Decimal("Infinity")


def booking_interval(booked: Totals, others, h: Decimal) -> Interval | None:
    """Give the interval of hour values at which the booked offer had the lowest effective cost.

    `others` are the totals of the other offers of the trip. Give None when no hour value
    makes the booked offer the best.
    """
    low, high = _LOW, _HIGH
    b_now, b_next = booked
    for x_now, x_next in others:
        if not (x_now.is_finite() and x_next.is_finite()):
            continue  # an offer with no rate gives no limit
        be = break_even(b_now, b_next, x_now, x_next, h)
        if be is None:
            if x_now < b_now:
                return None  # the other offer is cheaper at each hour value
            continue
        if be.better == "below":  # the other offer is better below the value
            low = max(low, be.hour_value)
        else:
            high = min(high, be.hour_value)
    if low > high:
        return None
    return (None if low == _LOW else low, None if high == _HIGH else high)


def best_fit(intervals) -> tuple[Decimal | None, Decimal | None, int, int] | None:
    """Give (low, high, count, total): the interval that the most intervals share.

    A tie gives the interval with the lowest low end. `total` counts all bookings, also those with
    no interval (None). Give None when no booking has an interval.
    """
    intervals = list(intervals)
    events = []
    for iv in intervals:
        if iv is None:
            continue
        low, high = iv
        events.append((_LOW if low is None else low, 0))  # a start comes before an end at the same value
        events.append((_HIGH if high is None else high, 1))
    if not events:
        return None
    events.sort()
    count = best = 0
    best_low = best_high = None
    is_open = False
    for value, kind in events:
        if kind == 0:
            count += 1
            if count > best:
                best, best_low, is_open = count, value, True
        else:
            if is_open:
                best_high, is_open = value, False
            count -= 1
    return (None if best_low == _LOW else best_low, None if best_high == _HIGH else best_high,
            best, len(intervals))
