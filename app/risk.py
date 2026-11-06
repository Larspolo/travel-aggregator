"""The risk extras of an offer (epic #172, docs/SPEC.md section 7.2 "Risky transfers")."""

from decimal import Decimal

from app.ranking import Weights


def self_transfer_extras(fare, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the penalty for each self-transfer of the fare (#176): one part with the sum. A penalty of 0 adds no part.

    The count is on the fare, not on the itinerary: one source can sell the journey as one ticket, another as two.
    """
    count = fare.self_transfers or 0
    penalty = Decimal(weights.self_transfer_penalty)
    if penalty == 0 or count == 0:
        return ()
    return (("self-transfer", penalty * count),)
