"""The short-transfer penalty of an itinerary (#173): a transfer shorter than a minimum costs a penalty."""

from datetime import timedelta
from decimal import Decimal

from app.ranking import Weights


def transfer_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add one part "short transfer" for the short transfers: the penalty times their count.

    A transfer is the time from the arrival of one leg to the departure of the next one (both UTC, so no offset is
    needed). A penalty of 0 adds no part.
    """
    penalty = Decimal(weights.short_transfer_penalty)
    if penalty == 0 or len(itinerary.legs) < 2:
        return ()
    minimum = timedelta(minutes=weights.short_transfer_min)
    short = sum(1 for before, after in zip(itinerary.legs, itinerary.legs[1:])
                if after.depart_at - before.arrive_at < minimum)
    if short == 0:
        return ()
    return (("short transfer", penalty * short),)
