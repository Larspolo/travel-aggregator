"""The CSV export of a trip (#701)."""

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import require_login
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Leg, Trip


def _itinerary(depart, arrive, offset, **kw):
    it = Itinerary(fingerprint=f"fp-{depart.hour}", mode_summary="train", depart_at=depart, arrive_at=arrive,
                   duration_min=int((arrive - depart).total_seconds() // 60), transfers=0, **kw)
    it.legs.append(Leg(seq=0, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                       to_name="Zürich", depart_at=depart, depart_offset_min=offset,
                       arrive_at=arrive, arrive_offset_min=offset))
    return it


@pytest.fixture
def trip_id(sessions):
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich",
                 date_from=date(2026, 12, 1), travelers=2, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=timezone.utc), datetime(2026, 12, 1, 15, tzinfo=timezone.utc),
                       60, pinned=True, note='=HYPERLINK("x")')
        a.legs[0].carrier = "+DB"
        fare = Fare(source="bahn", fare_name="Sparpreis", travel_class="2", flexibility="none",
                    booking_url="https://example.com/b", latest_price=Decimal("79.90"), currency="EUR",
                    latest_captured_at=datetime(2026, 11, 4, tzinfo=timezone.utc))
        fare.prices += [FarePrice(price=Decimal("79.90"), currency="EUR",
                                  captured_at=datetime(2026, 11, 4, tzinfo=timezone.utc))]
        a.fares.append(fare)
        b = _itinerary(datetime(2026, 12, 1, 10, tzinfo=timezone.utc), datetime(2026, 12, 1, 17, tzinfo=timezone.utc),
                       0, hidden=True, booked=True)
        t.itineraries += [a, b]
        s.add(t)
        s.commit()
        yield t.id


@pytest.fixture
def client():
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)


def _rows(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))


def test_the_export_is_a_csv_attachment_with_a_bom(client, trip_id):
    r = client.get(f"/trips/{trip_id}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.headers["content-disposition"] == f'attachment; filename="trip-{trip_id}-amsterdam-zurich.csv"'
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert "Zürich" in r.content.decode("utf-8-sig")


def test_one_header_row_and_one_row_per_fare(client, trip_id):
    header, *rows = _rows(client.get(f"/trips/{trip_id}/export.csv"))
    assert header == [
        "route", "departure", "arrival", "duration_min", "transfers", "modes", "carriers", "service_numbers",
        "source", "fare_name", "travel_class", "latest_price", "currency", "last_captured", "pinned", "hidden",
        "booked", "note", "booking_url", "paid",
    ]
    assert len(rows) == 1  # the second itinerary has no fare
    row = dict(zip(header, rows[0]))
    assert row["route"] == "Amsterdam - Zürich"
    assert row["departure"] == "2026-12-01T09:00:00+01:00"
    assert row["arrival"] == "2026-12-01T16:00:00+01:00"
    assert row["duration_min"] == "420" and row["transfers"] == "0"
    assert row["modes"] == "train"
    assert row["service_numbers"] == "ICE 105"
    assert row["source"] == "bahn" and row["fare_name"] == "Sparpreis" and row["travel_class"] == "2"
    assert row["latest_price"] == "79.90" and row["currency"] == "EUR"
    assert row["last_captured"] == "2026-11-04T00:00:00+00:00"
    assert (row["pinned"], row["hidden"], row["booked"]) == ("true", "false", "false")
    assert row["booking_url"] == "https://example.com/b"


def test_a_formula_like_cell_gets_a_leading_quote(client, trip_id):
    header, *rows = _rows(client.get(f"/trips/{trip_id}/export.csv"))
    row = dict(zip(header, rows[0]))
    assert row["note"] == '\'=HYPERLINK("x")'
    assert row["carriers"] == "'+DB"


def test_an_unknown_trip_is_404(client, sessions):
    assert client.get("/trips/999999/export.csv").status_code == 404


def test_no_login_goes_to_the_login_page(trip_id):
    r = TestClient(app).get(f"/trips/{trip_id}/export.csv", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
