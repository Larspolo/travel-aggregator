"""The hour values at which each booking was the best offer of its trip (epic #1708).

The totals come from `row_cost()` at the hour value `h` and at `h + 1`, as in `tradeoff_lines()`
of `app/web/pages.py`, with the prices of the time of each booking (#1710).
"""

import dataclasses
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Capture, Fare, Itinerary
from app.parsers import group_price
from app.ranking import Weights
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


class _At:
    """A read-only view of an object with some attributes replaced: the stored row does not change (#1710)."""

    def __init__(self, obj, **values):
        self._obj, self._values = obj, values

    def __getattr__(self, name):
        values = self.__dict__["_values"]
        return values[name] if name in values else getattr(self.__dict__["_obj"], name)


def _offer_at(it: Itinerary, at):
    """The itinerary with each fare at the price of its newest `FarePrice` at or before `at`, and the
    chosen prices; None when no fare had a price then."""
    fares, prices = [], {}
    for f in it.fares:
        before = [p for p in f.prices if p.captured_at <= at]
        if not before:
            continue
        p = max(before, key=lambda p: (p.captured_at, p.id))
        fares.append(_At(f, latest_price=p.price, currency=p.currency, latest_captured_at=p.captured_at))
        prices[f.id] = (p, f.source)
    if not fares:
        return None
    return _At(it, fares=fares), prices


def booking_intervals(session: Session, weights: Weights, places, rates, fees) -> list:
    """Give (itinerary, interval or None) for each booked or cancelled journey with a `booked_at`, in the
    order of `booked_at`: the hour values at which it had the lowest effective cost of its trip then.

    The offers are the itineraries of the trip that did not depart before `booked_at`, each fare at the
    price of its newest `FarePrice` at or before `booked_at`. A booking with no other offer gives None.
    """
    from app.door import trip_places
    from app.web.pages import row_cost  # here: the profile page will import this module

    booked = or_(Itinerary.booked.is_(True), Itinerary.cancelled_at.is_not(None))
    trip_ids = select(Itinerary.trip_id).where(booked, Itinerary.booked_at.is_not(None))
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id.in_(trip_ids))
                          .options(selectinload(Itinerary.legs), selectinload(Itinerary.trip),
                                   selectinload(Itinerary.fares).selectinload(Fare.prices))).all()
    # A trip with its own hour value (#2422) does not tell the hour value of the profile (#2426).
    bookings = sorted((it for it in its if it.booked_at is not None and (it.booked or it.cancelled_at is not None)
                       and getattr(it.trip, "hour_value", None) is None),
                      key=lambda it: (it.booked_at, it.id))
    higher = dataclasses.replace(weights, hour_markup=weights.hour_markup + 1)
    result = []
    own_places: dict = {}  # the places of each trip, loaded once per trip (#2109)
    for b in bookings:
        at = b.booked_at
        if b.trip_id not in own_places:
            own_places[b.trip_id] = trip_places(session, b.trip)
        trip_pl = own_places[b.trip_id]
        offers = [(it, o) for it in its if it.trip_id == b.trip_id and it.depart_at >= at
                  for o in [_offer_at(it, at)] if o is not None]
        counts = _travelers(session, [prices for _, (_, prices) in offers])
        stale_before = at - timedelta(hours=weights.stale_hours)

        def totals(view):
            return tuple(row_cost(view, view.fares, trip_pl, w, stale_before, rates, counts, fees)[1].total
                         for w in (weights, higher))
        mine = [view for it, (view, _) in offers if it.id == b.id]
        others = [totals(view) for it, (view, _) in offers if it.id != b.id]
        if not mine or not others:
            result.append((b, None))
            continue
        result.append((b, booking_interval(totals(mine[0]), others, weights.hour_markup)))
    return result


def _travelers(session: Session, offers) -> dict[int, int]:
    """The travelers of the chosen price of each fare whose source gives the price of the group, as
    `fare_travelers()` of `app/web/pages.py` does for the newest price (#767): only counts of 2 or more."""
    chosen = {fid: p.capture_id for prices in offers for fid, (p, source) in prices.items()
              if p.capture_id is not None and group_price(source)}
    if not chosen:
        return {}
    travelers = dict(session.execute(select(Capture.id, Capture.travelers)
                                     .where(Capture.id.in_(set(chosen.values())))).all())
    return {fid: n for fid, cid in chosen.items() if (n := travelers.get(cid)) is not None and n > 1}
