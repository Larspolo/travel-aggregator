"""The flexibility amount of a fare (docs/SPEC.md, section 7.2, #175).

Three tiers: non_refundable, partly_refundable, flexible. The ingest stores a free text; a known text maps to a tier.
An unknown or empty text gets no amount.
"""

from decimal import Decimal

from app.ranking import Weights

LABELS = {"non_refundable": "non-refundable", "partly_refundable": "partly refundable", "flexible": "flexible"}
ALIASES = {"nonrefundable": "non_refundable", "no_refund": "non_refundable", "saver": "non_refundable",
           "partly_refundable": "partly_refundable", "partially_refundable": "partly_refundable",
           "semi_flexible": "partly_refundable", "refundable": "flexible", "fully_refundable": "flexible",
           "flex": "flexible"}


def tier(text: str | None) -> str | None:
    """Give the tier of a flexibility text, or None for an unknown or empty text."""
    key = (text or "").strip().lower().replace("-", "_").replace(" ", "_")
    return key if key in LABELS else ALIASES.get(key)


def flexibility_extras(fare, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the signed amount of the tier of the fare (negative = bonus). An amount of 0 adds no part."""
    t = tier(fare.flexibility)
    if t is None:
        return ()
    amount = Decimal(getattr(weights, f"flex_{t}"))
    return ((LABELS[t], amount),) if amount != 0 else ()
