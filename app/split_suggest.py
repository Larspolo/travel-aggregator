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


def split_skip(trip) -> set[str]:
    """The names that are no transfer place to suggest for `trip` (#1459, #1460).

    The origin, the destination, their alternative places (comma-separated) and the via place of each split trip
    (the `destination_text` of a part that starts at the origin).
    """
    names = [trip.origin_text, trip.destination_text]
    for alt in (trip.origin_alt_text, trip.destination_alt_text):
        names += (alt or "").split(",")
    origin = (trip.origin_text or "").casefold()
    names += [part.destination_text for part in trip.split_trips if (part.origin_text or "").casefold() == origin]
    return {name.strip() for name in names if name and name.strip()}
