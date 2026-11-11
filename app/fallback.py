"""Transfers without a later captured connection (epic #1771): the input of the penalty (#1773) and the mark (#1774).

A transfer i of an itinerary is the pair legs[i], legs[i + 1]. It has a later connection when another itinerary of the
pool has a leg that departs from the place of the transfer later than legs[i + 1] and ends at the final station of the
itinerary on the same local day as the planned arrival (#1794). No database access: the caller gives the itineraries.
"""

import sys
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import object_session
from sqlalchemy.orm.attributes import set_committed_value

from app.risk import _name_key


def _key(code, name) -> str | None:
    """The code when it is set, else the name (no case, single spaces). None when neither is set."""
    if code:
        return "c:" + code.strip()
    name_key = _name_key(name or "")
    return "n:" + name_key if name_key else None


def _both_keys(code, name) -> list[str]:
    """The code key and the name key of a station: a leg is indexed under both (#1771)."""
    keys = []
    if code:
        keys.append("c:" + code.strip())
    name_key = _name_key(name or "")
    if name_key:
        keys.append("n:" + name_key)
    return keys


def _arrival_day(leg) -> date:
    """The local date of the arrival of a leg, by its stored offset (0 when the leg has no offset)."""
    return (leg.arrive_at + timedelta(minutes=getattr(leg, "arrive_offset_min", None) or 0)).date()


def build_index(pool) -> dict[tuple[str, str], list[tuple]]:
    """Map (departure key, final key) to the sorted (departure time, id of the itinerary, local arrival day at the
    final station) of the legs with these keys."""
    index: dict[tuple[str, str], list[tuple]] = {}
    for itinerary in pool:
        if not itinerary.legs:
            continue
        last = itinerary.legs[-1]
        finals = _both_keys(last.to_code, last.to_name)
        day = _arrival_day(last)
        for leg in itinerary.legs:
            for dep in _both_keys(leg.from_code, leg.from_name):
                for final in finals:
                    index.setdefault((dep, final), []).append((leg.depart_at, id(itinerary), day))
    for entries in index.values():
        entries.sort()
    return index


def _has_later(entries, depart_at, own_id, day) -> bool:
    """True when an entry of another itinerary departs after `depart_at` and arrives on the local day `day`."""
    start = bisect_right(entries, (depart_at, sys.maxsize))
    return any(owner != own_id and arrives == day for _, owner, arrives in entries[start:])


def no_fallback(it, index) -> list[int]:
    """The indexes i of the transfers of `it` that have no later captured connection in the indexed pool (#1771).

    An itinerary with one leg has no transfer and gives []. The itinerary itself is never its own connection.
    """
    if len(it.legs) < 2:
        return []
    last = it.legs[-1]
    final = _key(last.to_code, last.to_name)
    day = _arrival_day(last)
    result = []
    for i, (before, after) in enumerate(zip(it.legs, it.legs[1:])):
        place = _key(before.to_code, before.to_name)
        entries = index.get((place, final), []) if place is not None and final is not None else []
        if not _has_later(entries, after.depart_at, id(it), day):
            result.append(i)
    return result


def fallback_index(session, trip_id: int, now: datetime):
    """The index of the not-departed itineraries of the trip (also hidden ones), with two queries, built once per request (#1773).

    The SQLAlchemy session dict (`session.info`) keeps it for the request (P4).
    """
    from app.models import Itinerary, Leg

    cache = session.info.setdefault("fallback_index", {})
    if trip_id not in cache:
        pool = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.depart_at > now)).all()
        # One query for the legs of all of them: selectinload sends one query per 500 itineraries (#1774).
        legs: dict[int, list] = {it.id: [] for it in pool}
        for leg in session.scalars(select(Leg).join(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.depart_at > now)
                                   .order_by(Leg.itinerary_id, Leg.seq)):
            legs[leg.itinerary_id].append(leg)
        for it in pool:
            if "legs" not in it.__dict__:
                set_committed_value(it, "legs", legs[it.id])
        cache[trip_id] = build_index(pool)
    return cache[trip_id]


def fallback_extras(it, weights) -> tuple[tuple[str, Decimal], ...]:
    """The part "no later connection": the penalty times the transfers with no later connection (#1773).

    A penalty of 0, an itinerary with one leg or one with no session adds no part and runs no query.
    """
    penalty = Decimal(weights.no_fallback_penalty)
    if penalty == 0 or len(it.legs) < 2:
        return ()
    session = object_session(it)
    if session is None:
        return ()
    count = len(no_fallback(it, fallback_index(session, it.trip_id, datetime.now(timezone.utc))))
    return (("no later connection", penalty * count),) if count else ()


def no_fallback_marks(it) -> list[int]:
    """The transfers of `it` with no later captured connection, for the mark of the row (#1774); also with a penalty of 0."""
    session = object_session(it)
    if session is None or len(it.legs) < 2:
        return []
    return no_fallback(it, fallback_index(session, it.trip_id, datetime.now(timezone.utc)))
