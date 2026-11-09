"""The transfer places of the itineraries of a trip, most frequent first (#1458)."""

from collections.abc import Iterable


def via_places(itineraries: Iterable, skip: Iterable[str], limit: int = 5) -> list[tuple[str, int]]:
    """Return up to `limit` (place, count) pairs of the transfer places.

    A transfer place is the `to_name` of each leg but the last. A place counts once per
    itinerary. Names are the same when their `casefold()` is the same; the place shows the
    spelling of its first itinerary in the input order. Names in `skip` do not show.
    Order: count (highest first), then the name A to Z.
    """
    hidden = {name.strip().casefold() for name in skip}
    counts: dict[str, int] = {}
    spelling: dict[str, str] = {}

    for itinerary in itineraries:
        legs = sorted(itinerary.legs, key=lambda leg: leg.seq)
        seen: set[str] = set()
        for leg in legs[:-1]:
            name = leg.to_name.strip()
            key = name.casefold()
            if not name or key in hidden:
                continue
            spelling.setdefault(key, name)
            seen.add(key)
        for key in seen:
            counts[key] = counts.get(key, 0) + 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], spelling[item[0]]))
    return [(spelling[key], count) for key, count in ranked[:limit]]
