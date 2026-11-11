"""The 1st class amount of a fare (#691): a signed amount per hour of the itinerary (negative = bonus)."""
from decimal import Decimal

from app.ranking import Weights


def class_extras(fare, duration_min: int, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """The part "1st class" for a 1st class fare; none for another class or an amount of 0."""
    amount = Decimal(weights.first_class_hour)
    if fare.travel_class != "first" or amount == 0:
        return ()
    return (("1st class", amount * duration_min / 60),)
