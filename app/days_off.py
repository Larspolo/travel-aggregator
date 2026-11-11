"""The days off of the owner (#2371, epic #2331): a day off counts as a weekend day in the work-hour markup.

The set of days is built once per request and kept in `session.info`, as `app/fallback.py` keeps its index (#1773).
"""

from datetime import date, timedelta

from sqlalchemy import select


def days_off(session) -> frozenset[date]:
    """Each date from the `first_day` to the `last_day` of each `DayOff` row (#2370), both included."""
    from app.models import DayOff

    cache = session.info
    if "days_off" not in cache:
        days: set[date] = set()
        for row in session.scalars(select(DayOff)):
            day = row.first_day
            while day <= row.last_day:
                days.add(day)
                day += timedelta(days=1)
        cache["days_off"] = frozenset(days)
    return cache["days_off"]
