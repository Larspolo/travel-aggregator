"""The risk extras of an offer (epic #172, docs/SPEC.md section 7.2 "Risky transfers") and the mode markup (#174)."""

from datetime import timedelta
from decimal import Decimal

from app.ranking import Weights

MODE_FIELDS = {"train": "train_markup", "bus": "bus_markup", "flight": "flight_markup", "ferry": "ferry_markup"}


def mode_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("<mode> markup", amount) for each mode of the itinerary that has a markup. A negative amount is a
    discount. A markup of 0 adds no part. The modes come from `mode_summary` ("train+bus")."""
    parts = []
    for mode in dict.fromkeys(m for m in (itinerary.mode_summary or "").split("+") if m):
        field = MODE_FIELDS.get(mode)
        amount = Decimal(getattr(weights, field)) if field else Decimal("0")
        if amount != 0:
            parts.append((f"{mode} markup", amount))
    return tuple(parts)


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


def self_transfer_extras(fare, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the penalty for each self-transfer of the fare (#176): one part with the sum. A penalty of 0 adds no part.

    The count is on the fare, not on the itinerary: one source can sell the journey as one ticket, another as two.
    """
    count = fare.self_transfers or 0
    penalty = Decimal(weights.self_transfer_penalty)
    if penalty == 0 or count == 0:
        return ()
    return (("self-transfer", penalty * count),)
