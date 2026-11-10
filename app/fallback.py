"""Transfers without a later captured connection (epic #1771): the input of the penalty (#1773) and the mark (#1774).

A transfer i of an itinerary is the pair legs[i], legs[i + 1]. It has a later connection when another itinerary of the
pool has a leg that departs from the place of the transfer later than legs[i + 1] and ends at the final station of the
itinerary. No database access: the caller gives the itineraries.
"""

import sys
from bisect import bisect_right

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


def build_index(pool) -> dict[tuple[str, str], list[tuple]]:
    """Map (departure key, final key) to the sorted (departure time, id of the itinerary) of the legs with these keys."""
    index: dict[tuple[str, str], list[tuple]] = {}
    for itinerary in pool:
        if not itinerary.legs:
            continue
        last = itinerary.legs[-1]
        finals = _both_keys(last.to_code, last.to_name)
        for leg in itinerary.legs:
            for dep in _both_keys(leg.from_code, leg.from_name):
                for final in finals:
                    index.setdefault((dep, final), []).append((leg.depart_at, id(itinerary)))
    for entries in index.values():
        entries.sort()
    return index


def _has_later(entries, depart_at, own_id) -> bool:
    """True when an entry of another itinerary departs after `depart_at`."""
    start = bisect_right(entries, (depart_at, sys.maxsize))
    return any(owner != own_id for _, owner in entries[start:])


def no_fallback(it, index) -> list[int]:
    """The indexes i of the transfers of `it` that have no later captured connection in the indexed pool (#1771).

    An itinerary with one leg has no transfer and gives []. The itinerary itself is never its own connection.
    """
    if len(it.legs) < 2:
        return []
    last = it.legs[-1]
    final = _key(last.to_code, last.to_name)
    result = []
    for i, (before, after) in enumerate(zip(it.legs, it.legs[1:])):
        place = _key(before.to_code, before.to_name)
        entries = index.get((place, final), []) if place is not None and final is not None else []
        if not _has_later(entries, after.depart_at, id(it)):
            result.append(i)
    return result
