"""The search reminder waits for the first sales date of the sources with a booking horizon (#2275, epic #2252)."""

from datetime import UTC, datetime, timedelta

from app import reminder
from app.models import Itinerary, Setting, Trip
from app.reminder import due_reminders
from tests.test_reminder_cases import engine  # noqa: F401  (fixture)

from sqlalchemy.orm import Session


def _trip(s: Session, date_from) -> Trip:
    trip = Trip(title="Amsterdam – Zürich", status="planning", date_from=date_from,
                origin_text="Amsterdam", destination_text="Zürich")
    s.add(trip)
    s.flush()
    depart = datetime(date_from.year, date_from.month, date_from.day, 8, tzinfo=UTC)
    s.add(Itinerary(trip_id=trip.id, fingerprint=f"f{trip.id}", depart_at=depart,
                    arrive_at=depart + timedelta(hours=1), duration_min=60, pinned=True))
    s.flush()
    return trip


def _settings(s: Session, horizon: str | None) -> None:
    s.merge(Setting(key=reminder.REMINDER_DAYS_KEY, value="3"))
    s.merge(Setting(key=reminder.REMINDER_BEFORE_KEY, value="400"))
    if horizon is not None:
        s.merge(Setting(key="sales_horizon:bahn.de", value=horizon))


def _titles(s: Session, now: datetime) -> list[str]:
    return [t.title for t in due_reminders(s, now)]


def test_a_trip_before_the_sales_date_gets_no_reminder(engine):  # noqa: F811
    from datetime import date
    from sqlalchemy.orm import sessionmaker

    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    with sessionmaker(bind=engine)() as s:
        _settings(s, "180")
        _trip(s, date(2027, 6, 1))
        s.commit()
        assert _titles(s, now) == []


def test_a_trip_after_the_sales_date_gets_its_reminder(engine):  # noqa: F811
    from datetime import date
    from sqlalchemy.orm import sessionmaker

    with sessionmaker(bind=engine)() as s:
        _settings(s, "180")
        _trip(s, date(2027, 6, 1))
        s.commit()
        assert _titles(s, datetime(2026, 12, 3, 12, 0, tzinfo=UTC)) == ["Amsterdam – Zürich"]
        assert _titles(s, datetime(2026, 12, 4, 12, 0, tzinfo=UTC)) == ["Amsterdam – Zürich"]


def test_a_trip_with_no_horizon_gets_its_reminder(engine):  # noqa: F811
    from datetime import date
    from sqlalchemy.orm import sessionmaker

    with sessionmaker(bind=engine)() as s:
        _settings(s, None)
        _trip(s, date(2027, 6, 1))
        s.commit()
        assert _titles(s, datetime(2026, 11, 11, 12, 0, tzinfo=UTC)) == ["Amsterdam – Zürich"]
