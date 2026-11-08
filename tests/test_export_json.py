"""The JSON export of a trip (#700)."""

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
                 date_from=date(2026, 12, 1), travelers=2, status="planning", notes="ski")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=timezone.utc), datetime(2026, 12, 1, 15, tzinfo=timezone.utc),
                       60, pinned=True, note="best")
        fare = Fare(source="bahn", fare_name="Sparpreis", travel_class="2", flexibility="none",
                    booking_url="https://example.com/b", latest_price=Decimal("79.90"), currency="EUR",
                    latest_captured_at=datetime(2026, 11, 4, tzinfo=timezone.utc))
        fare.prices += [FarePrice(price=Decimal("89.90"), currency="EUR",
                                  captured_at=datetime(2026, 11, 3, tzinfo=timezone.utc)),
                        FarePrice(price=Decimal("79.90"), currency="EUR",
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


def test_the_export_is_a_json_attachment_with_all_data(client, trip_id):
    r = client.get(f"/trips/{trip_id}/export.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["content-disposition"] == f'attachment; filename="trip-{trip_id}-amsterdam-zurich.json"'
    data = r.json()
    assert data["format"] == "travel-aggregator-trip-export" and data["version"] == 1
    assert datetime.fromisoformat(data["exported_at"]).tzinfo is not None
    assert data["trip"] == {"id": trip_id, "title": "Amsterdam – Zürich", "origin": "Amsterdam",
                            "destination": "Zürich", "date_from": "2026-12-01", "date_to": None,
                            "travelers": 2, "status": "planning", "notes": "ski", "target_price": None}
    a, b = data["itineraries"]
    assert (a["pinned"], a["hidden"], a["booked"], a["note"]) == (True, False, False, "best")
    assert (b["pinned"], b["hidden"], b["booked"]) == (False, True, True)
    assert a["legs"][0]["depart_at"] == "2026-12-01T09:00:00+01:00"
    assert a["legs"][0]["arrive_at"] == "2026-12-01T16:00:00+01:00"
    assert b["legs"][0]["depart_at"] == "2026-12-01T10:00:00+00:00"
    (fare,) = a["fares"]
    assert {k: fare[k] for k in ("source", "fare_name", "travel_class", "flexibility", "booking_url")} == {
        "source": "bahn", "fare_name": "Sparpreis", "travel_class": "2", "flexibility": "none",
        "booking_url": "https://example.com/b"}
    assert fare["latest_price"] == "79.90"
    assert [(p["price"], p["currency"]) for p in fare["prices"]] == [("89.90", "EUR"), ("79.90", "EUR")]
    assert all(isinstance(p["price"], str) for p in fare["prices"])
    assert fare["prices"][0]["captured_at"].startswith("2026-11-03T00:00:00")
    assert b["fares"] == []


def test_an_unknown_trip_is_404(client, sessions):
    assert client.get("/trips/999999/export.json").status_code == 404


def test_no_login_goes_to_the_login_page(trip_id):
    r = TestClient(app).get(f"/trips/{trip_id}/export.json", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
