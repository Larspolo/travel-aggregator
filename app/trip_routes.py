"""The routes of the shown rows of a trip (trip:routes, #2224)."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Route:
    """One route: the rows with the same transfer places.

    `key` is the tuple of the casefolded transfer places in leg order; `label` is "Direct" or "via A, B" with the
    spelling of the first row; `best` is the row with the lowest effective cost; `diff` is that cost minus the best
    cost of the trip; `cheapest` is the lowest price of the rows of the route.
    """

    key: tuple
    label: str
    count: int
    best: tuple
    diff: Decimal
    cheapest: Decimal


def trip_routes(rows) -> list[Route]:
    """The routes of `rows`, the `(itinerary, fare, cost)` tuples of `trip_page()`.

    A row with no rate does not count. The best row of a route has the lowest effective cost; a tie goes to the
    earliest departure. The result is ordered by the best effective cost, then by the label.
    """
    from app.web.pages import local

    groups: dict[tuple, dict] = {}
    for row in rows:
        it, _fare, cost = row
        if cost.no_rate:
            continue
        places = _places(it)
        key = tuple(name.casefold() for name in places)
        group = groups.get(key)
        if group is None:
            label = "via " + ", ".join(places) if places else "Direct"
            group = groups[key] = {"key": key, "label": label, "count": 0, "best": None, "cheapest": None}
        group["count"] += 1
        rank = (cost.total, _departure(it, local))
        if group["best"] is None or rank < group["best"][0]:
            group["best"] = (rank, row)
        if group["cheapest"] is None or cost.price < group["cheapest"]:
            group["cheapest"] = cost.price

    if not groups:
        return []
    lowest = min(group["best"][0][0] for group in groups.values())
    routes = [
        Route(key=group["key"], label=group["label"], count=group["count"], best=group["best"][1],
              diff=group["best"][0][0] - lowest, cheapest=group["cheapest"])
        for group in groups.values()
    ]
    return sorted(routes, key=lambda route: (route.best[2].total, route.label))


def _places(it) -> list[str]:
    """The `to_name` of each leg but the last, in leg order (the spelling of the itinerary)."""
    legs = sorted(it.legs, key=lambda leg: leg.seq)
    return [leg.to_name.strip() for leg in legs[:-1] if leg.to_name.strip()]


def _departure(it, local):
    first = it.legs[0]
    return local(first.depart_at, first.depart_offset_min)
