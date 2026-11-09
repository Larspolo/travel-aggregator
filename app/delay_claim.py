"""The EU rail compensation of a delayed booked journey (#1691): 25 % of the paid price from 60 minutes of arrival
delay, 50 % from 120 minutes. Only a journey with train legs only can claim."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models import Itinerary

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Claim:
    percent: int
    amount: Decimal
    currency: str


def claim(it: Itinerary) -> Claim | None:
    """The claim of the itinerary, or None when it cannot claim."""
    if not it.booked or it.booked_price is None or it.delay_min is None or it.delay_min < 60:
        return None
    if not it.legs or any(leg.mode != "train" for leg in it.legs):
        return None
    percent = 50 if it.delay_min >= 120 else 25
    amount = (Decimal(it.booked_price) * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return Claim(percent, amount, it.booked_currency or "EUR")
