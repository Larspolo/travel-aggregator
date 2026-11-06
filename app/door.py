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
