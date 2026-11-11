"""The trip page shows the form "Cancel booking" and the cancelled booking (#1686)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=3)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _add(sessions, booked=True):
    leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 777", from_name="A", to_name="B",
              depart_at=SOON, depart_offset_min=60, arrive_at=SOON + timedelta(hours=2), arrive_offset_min=60)
    trip = Trip(title="T", origin_text="A", destination_text="B", status="planning", date_from=SOON.date())
    it = Itinerary(fingerprint="f", depart_at=SOON, arrive_at=SOON + timedelta(hours=2), duration_min=120,
                   booked=booked, booked_price=Decimal("89") if booked else None,
                   booked_currency="EUR" if booked else None, legs=[leg])
    Fare(itinerary=it, source="ns", latest_price=Decimal("89"), currency="EUR", latest_captured_at=SOON)
    trip.itineraries = [it]
    with sessions() as s:
        s.add(trip)
        s.commit()
        return trip.id, it.id


def test_a_booked_row_has_the_cancel_form_with_a_labelled_refund(client, sessions):
    tid, iid = _add(sessions)
    html = client.get(f"/trips/{tid}").text
    assert f'action="/trips/{tid}/itineraries/{iid}/cancel"' in html
    assert f'<label for="refund-{iid}">Refund</label>' in html
    assert f'id="refund-{iid}" name="refund" inputmode="decimal" value="0"' in html
    assert "Cancel booking" in html


def test_a_row_that_is_not_booked_has_no_cancel_form(client, sessions):
    tid, iid = _add(sessions, booked=False)
    assert "/cancel" not in client.get(f"/trips/{tid}").text


def test_a_cancelled_row_shows_paid_and_refund_and_no_badge(client, sessions):
    tid, iid = _add(sessions)
    page = client.get(f"/trips/{tid}").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post(f"/trips/{tid}/itineraries/{iid}/cancel", data={"csrf_token": token, "refund": "60"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{tid}"
    html = client.get(f"/trips/{tid}").text
    assert "Booking cancelled: paid €89.00, refund €60.00" in html
    assert 'class="badge booked"' not in html
    assert "/cancel" not in html
