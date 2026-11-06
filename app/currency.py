"""Exchange rates to EUR and the conversion of an amount to EUR (#383). Money is `Decimal`, never `float`."""

from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CurrencyRate

CENT = Decimal("0.01")
EUR = "EUR"


def load_rates(session: Session) -> dict[str, Decimal]:
    """The stored rates: the code of a currency to its EUR value for one unit."""
    rows = session.scalars(select(CurrencyRate)).all()
    return {row.code: row.eur_per_unit for row in rows}


def to_eur(amount: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal | None:
    """The amount in EUR, rounded to cents. `None` when the currency has no rate."""
    if currency == EUR:
        return amount
    rate = rates.get(currency)
    if rate is None:
        return None
    return (amount * rate).quantize(CENT, rounding=ROUND_HALF_EVEN)
