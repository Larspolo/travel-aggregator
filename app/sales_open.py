"""The first sales date of a trip per source (#2253, epic #2252).

Each source has a booking horizon: the number of days before the trip date when the source opens its sales.
The owner sets it as a `Setting` row with the key `sales_horizon:<source>`. No migration is needed.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting

HORIZON_KEY = "sales_horizon:{source}"
PREFIX = HORIZON_KEY.split("{", 1)[0]
MIN_DAYS = 1
MAX_DAYS = 999


def horizons(session: Session) -> dict[str, int]:
    """The horizon in days per source. A blank or bad value (not a whole number from 1 to 999) is no horizon."""
    result: dict[str, int] = {}
    rows = session.scalars(select(Setting).where(Setting.key.startswith(PREFIX)))
    for row in rows:
        value = row.value.strip()
        if not (value.isascii() and value.isdecimal()):
            continue
        days = int(value)
        if MIN_DAYS <= days <= MAX_DAYS:
            result[row.key[len(PREFIX):]] = days
    return result


def sales_open_on(trip_date: date, horizon: int | None) -> date | None:
    """The first sales date: the trip date minus the horizon. None with no horizon."""
    if horizon is None:
        return None
    return trip_date - timedelta(days=horizon)
