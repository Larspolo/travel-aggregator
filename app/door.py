"""The door-to-door extras of an itinerary (#94): the parts of the effective cost outside the vehicle."""

from decimal import Decimal

from app.currency import to_eur
from app.ranking import Weights

FLIGHT = "flight"  # app/schemas.py, Mode


def flight_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Give the airport time when a leg is a flight; no flight leg gives no extra (#99). The bag: `baggage_extras()`."""
    if not any(leg.mode == FLIGHT for leg in itinerary.legs):
        return ()
    minutes = weights.airport_before_min + weights.airport_after_min
    rate = weights.hour_markup if weights.flight_hour_markup is None else weights.flight_hour_markup  # (#1567)
    return (("airport time", Decimal(minutes) * rate / 60),)


def baggage_extras(fare, itinerary, weights: Weights, rates=None) -> tuple[tuple[str, Decimal], ...]:
    """Give the checked bag of a flight fare (#1527): an included bag is €0, a bag price of the fare is its EUR value
    (per traveler), else the flat baggage fee. No flight leg or a baggage fee of 0 gives no extra."""
    if not weights.baggage_fee or not any(leg.mode == FLIGHT for leg in itinerary.legs):
        return ()
    if (getattr(fare, "checked_bags_included", None) or 0) >= 1:
        return (("baggage (included)", Decimal(0)),)
    price = getattr(fare, "checked_bag_price", None)
    if price is not None:
        eur = to_eur(Decimal(price), fare.currency, rates or {})
        if eur is not None:
            return (("baggage", eur),)
    return (("baggage (estimate)", Decimal(weights.baggage_fee)),)


def _key(text: str) -> str:
    return text.strip().casefold()


def _matched(itinerary, places) -> list[tuple[str, object]]:
    """Give the (kind, place) pairs of the first and last station; no match adds nothing (#98)."""
    if not itinerary.legs:
        return []
    found: dict[tuple[str, str], object] = {}
    for p in sorted(places, key=lambda p: p.id):
        found.setdefault((p.kind, _key(p.place_text)), p)
    matched = []
    for kind, name in (("access", itinerary.legs[0].from_name), ("egress", itinerary.legs[-1].to_name)):
        p = found.get((kind, _key(name)))
        if p is not None:
            matched.append((kind, p))
    return matched


def door_extras(itinerary, places, hour_markup: Decimal) -> tuple[tuple[str, Decimal], ...]:
    """Give the time and cost to reach the first station and to leave the last station (#98).

    The first leg `from_name` matches a place of kind "access", the last leg `to_name` a place of kind "egress"
    (case and outer spaces do not count; with two equal texts, the first by id). No match adds nothing.
    """
    extras: list[tuple[str, Decimal]] = []
    matched = _matched(itinerary, places)
    for kind, p in matched:
        extras += [(f"{kind} time", Decimal(p.minutes) * hour_markup / 60), (f"{kind} cost", Decimal(p.cost))]
    if itinerary.legs:  # (#2052) a kind with places but no match shows €0, so the owner sees the gap
        stations = (("access", itinerary.legs[0].from_name), ("egress", itinerary.legs[-1].to_name))
        for kind, name in stations:
            if any(p.kind == kind for p in places) and kind not in {k for k, _ in matched}:
                extras.append((f"no {kind} place for {name}", Decimal(0)))
    return tuple(extras)


def door_minutes(itinerary, places, weights: Weights) -> int:
    """Give the door-to-door minutes: the travel time, the access and egress minutes of the matched places (#98),
    and the airport time when a leg is a flight (#99). No match and no flight give the travel time."""
    minutes = itinerary.duration_min
    minutes += sum(p.minutes for _, p in _matched(itinerary, places))
    if any(leg.mode == FLIGHT for leg in itinerary.legs):
        minutes += weights.airport_before_min + weights.airport_after_min
    return minutes


_PLACE_GAPS = ("no access place for ", "no egress place for ")


def _estimate(label: str) -> bool:
    return label == "baggage (estimate)" or label.startswith(_PLACE_GAPS)


def estimate_count(rows) -> int:
    """Give the count of (itinerary, fare, cost) rows with an estimated part in the breakdown (#2053)."""
    return sum(1 for _, _, cost in rows if any(_estimate(label) for label, _ in cost.extras))


def has_place_gap(rows) -> bool:
    """Give True when a row has a "no access/egress place for" line: the trip page links to /places (#2053)."""
    return any(label.startswith(_PLACE_GAPS) for _, _, cost in rows for label, _ in cost.extras)
