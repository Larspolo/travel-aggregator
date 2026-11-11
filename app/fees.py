"""The booking fee of each source in EUR (#1142), for the score (#1143). Money is `Decimal`, never `float`."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceFee


def load_fees(session: Session) -> dict[str, Decimal]:
    """The stored fees: the source to its booking fee in EUR. A source with no row has no fee."""
    return {row.source: row.amount for row in session.scalars(select(SourceFee)).all()}
