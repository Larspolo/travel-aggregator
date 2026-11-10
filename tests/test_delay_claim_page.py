"""The trip page shows the delay form of a booked row that arrived and the claim (#1692)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import departed
from app.auth import make_password_hash
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip

PASSWORD = "pw"
NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=1)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setattr(departed, "clock", lambda: NOW)
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _add(sessions, delay=None, mode="train", depart=PAST, booked=True, paid_claim=False):
    leg = Leg(seq=0, mode=mode, carrier="NS", service_no="IC 777", from_name="A", to_name="B",
              depart_at=depart, depart_offset_min=60, arrive_at=depart + timedelta(hours=2), arrive_offset_min=60)
    trip = Trip(title="T", origin_text="A", destination_text="B", status="planning", date_from=depart.date())
    it = Itinerary(fingerprint="f", depart_at=depart, arrive_at=depart + timedelta(hours=2), duration_min=120,
                   booked=booked, booked_price=Decimal("90") if booked else None,
                   booked_currency="EUR" if booked else None, delay_min=delay,
                   claim_paid_at=NOW if paid_claim else None, legs=[leg])
    Fare(itinerary=it, source="ns", latest_price=Decimal("90"), currency="EUR", latest_captured_at=depart)
    trip.itineraries = [it]
    with sessions() as s:
        s.add(trip)
        s.commit()
        return trip.id, it.id


@pytest.mark.parametrize("delay,text", [(75, "Claim €22.50 (25 % for a delay of 75 min)"),
                                        (130, "Claim €45.00 (50 % for a delay of 130 min)")])
def test_a_late_train_row_shows_the_claim(client, sessions, delay, text):
    tid, _ = _add(sessions, delay)
    html = client.get(f"/trips/{tid}").text
    assert text in html and "claim paid" not in html


@pytest.mark.parametrize("kw", [{"delay": 40}, {"delay": 75, "mode": "bus"},
                                {"delay": 75, "depart": NOW + timedelta(days=1)}])
def test_no_claim_text_for_a_short_delay_a_bus_or_no_arrival(client, sessions, kw):
    tid, _ = _add(sessions, **kw)
    assert "Claim €" not in client.get(f"/trips/{tid}").text


def test_a_paid_claim_shows_claim_paid(client, sessions):
    tid, _ = _add(sessions, 75, paid_claim=True)
    assert "claim paid" in client.get(f"/trips/{tid}").text


def test_only_a_booked_row_that_arrived_has_the_delay_form(client, sessions):
    tid, iid = _add(sessions)
    html = client.get(f"/trips/{tid}").text
    assert f'action="/trips/{tid}/itineraries/{iid}/delay"' in html
    assert f'<label for="delay-{iid}">Delay at arrival (min)</label>' in html
    assert 'inputmode="numeric"' in html
    tid2, _ = _add(sessions, depart=NOW + timedelta(days=1))
    assert "/delay" not in client.get(f"/trips/{tid2}").text


def test_a_row_that_is_not_booked_has_no_delay_form(client, sessions):
    tid, _ = _add(sessions, booked=False, depart=NOW + timedelta(days=1))
    assert "/delay" not in client.get(f"/trips/{tid}").text


def test_save_delay_shows_the_claim(client, sessions):
    tid, iid = _add(sessions)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{tid}").text).group(1)
    r = client.post(f"/trips/{tid}/itineraries/{iid}/delay", data={"csrf_token": token, "minutes": "75"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "Claim €22.50 (25 % for a delay of 75 min)" in client.get(f"/trips/{tid}").text
