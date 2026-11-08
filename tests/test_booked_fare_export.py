"""The paid fare, price, currency and time in the JSON and CSV export and in the import (#1150)."""

import copy
import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import require_login
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Leg, Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export

UTC = timezone.utc
PAID_AT = datetime(2026, 11, 5, 9, 30, tzinfo=timezone(timedelta(hours=1)))


def _fare(name, price, at):
    fare = Fare(source="bahn", fare_name=name, travel_class="2", flexibility="none",
                booking_url="https://example.com/b", latest_price=Decimal(price), currency="EUR",
                latest_captured_at=at)
    fare.prices.append(FarePrice(price=Decimal(price), currency="EUR", captured_at=at))
    return fare


@pytest.fixture
def paid_trip(sessions):
    """A trip with one booked itinerary whose paid fare is the second of its two fares."""
    day = datetime(2026, 11, 4, tzinfo=UTC)
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich",
                 date_from=date(2026, 12, 1), travelers=2, status="planning")
        it = Itinerary(fingerprint="fp-paid", mode_summary="train", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC),
                       arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), duration_min=420, transfers=0, booked=True,
                       booked_price=Decimal("150.00"), booked_currency="EUR", booked_at=PAID_AT.astimezone(UTC))
        it.legs.append(Leg(seq=1, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                           to_name="Zürich", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC), depart_offset_min=0,
                           arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), arrive_offset_min=0))
        it.fares += [_fare("Sparpreis", "89.90", day), _fare("Flexpreis", "150.00", day)]
        t.itineraries.append(it)
        s.add(t)
        s.commit()
        it.booked_fare_id = it.fares[1].id
        s.commit()
        return t.id


def _paid(itinerary):
    return {k: itinerary[k] for k in ("booked_price", "booked_currency", "booked_at", "booked_fare")}


def test_the_export_keeps_the_paid_fare_price_currency_and_time(sessions, paid_trip):
    with sessions() as s:
        data = trip_export(load_trip(s, paid_trip))
    it = data["itineraries"][0]
    assert _paid(it) == {"booked_price": "150.00", "booked_currency": "EUR",
                         "booked_at": "2026-11-05T08:30:00+00:00", "booked_fare": 1}


def test_an_import_into_an_empty_database_gives_the_same_paid_fare(sessions, paid_trip):
    with sessions() as s:
        data = trip_export(load_trip(s, paid_trip))
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        new_trip = load_trip(s, r.trip_id)
        again = trip_export(new_trip)
        it = new_trip.itineraries[0]
        paid_fare = s.get(Fare, it.booked_fare_id)
        assert (it.booked_price, it.booked_currency) == (Decimal("150.00"), "EUR")
        assert it.booked_at == PAID_AT and it.booked_at.utcoffset() == timedelta(0)
        assert paid_fare.fare_name == "Flexpreis" and paid_fare.latest_price == Decimal("150.00")
    assert _paid(again["itineraries"][0]) == _paid(data["itineraries"][0])


def test_an_export_with_no_booked_price_key_imports_with_no_paid_price(sessions, paid_trip):
    with sessions() as s:
        data = trip_export(load_trip(s, paid_trip))
    for key in ("booked_price", "booked_currency", "booked_at", "booked_fare"):
        del data["itineraries"][0][key]
    with sessions() as s:
        r = import_trip(s, data)
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert it.booked is True
        assert (it.booked_price, it.booked_currency, it.booked_at, it.booked_fare_id) == (None, None, None, None)


def test_a_paid_fare_index_outside_the_fares_is_a_value_error(sessions, paid_trip):
    with sessions() as s:
        data = trip_export(load_trip(s, paid_trip))
    data["itineraries"][0]["booked_fare"] = 5
    with sessions() as s:
        with pytest.raises(ValueError, match="not valid"):
            import_trip(s, data)
        s.rollback()
        assert s.scalar(select(Trip.id).where(Trip.title == "Amsterdam – Zürich")) == paid_trip


@pytest.fixture
def client():
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)


def test_the_csv_has_the_paid_price_only_on_the_paid_fare(client, paid_trip):
    r = client.get(f"/trips/{paid_trip}/export.csv")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"), newline="")))
    paid_col = rows[0].index("paid")
    assert [row[paid_col] for row in rows[1:]] == ["", "150.00"]
