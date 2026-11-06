"""The door-to-door extras of an itinerary (#94): the parts of the effective cost outside the vehicle."""

from decimal import Decimal

from app.ranking import Weights

FLIGHT = "flight"  # app/schemas.py, Mode


def flight_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Give the airport time and the baggage fee when a leg is a flight; no flight leg gives no extra (#99)."""
    if not any(leg.mode == FLIGHT for leg in itinerary.legs):
        return ()
    minutes = weights.airport_before_min + weights.airport_after_min
    return (("airport time", Decimal(minutes) * weights.hour_markup / 60), ("baggage", Decimal(weights.baggage_fee)))


def _key(text: str) -> str:
    return text.strip().casefold()


def door_extras(itinerary, places, hour_markup: Decimal) -> tuple[tuple[str, Decimal], ...]:
    """Give the time and cost to reach the first station and to leave the last station (#98).

    The first leg `from_name` matches a place of kind "access", the last leg `to_name` a place of kind "egress"
    (case and outer spaces do not count; with two equal texts, the first by id). No match adds nothing.
    """
    if not itinerary.legs:
        return ()
    found: dict[tuple[str, str], object] = {}
    for p in sorted(places, key=lambda p: p.id):
        found.setdefault((p.kind, _key(p.place_text)), p)
    extras: list[tuple[str, Decimal]] = []
    for kind, name in (("access", itinerary.legs[0].from_name), ("egress", itinerary.legs[-1].to_name)):
        p = found.get((kind, _key(name)))
        if p is not None:
            extras += [(f"{kind} time", Decimal(p.minutes) * hour_markup / 60), (f"{kind} cost", Decimal(p.cost))]
    return tuple(extras)
