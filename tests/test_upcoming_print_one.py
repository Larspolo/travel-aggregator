"""The Upcoming page prints one booked journey with ?only=<id> (#1350)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(hour=7, minute=12, second=0, microsecond=0) + timedelta(days=10)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(s, title, depart, booked=True, price=None, service="IC 1"):
    trip = Trip(title=title, origin_text="A", destination_text="B", status="planning")
    arrive = depart + timedelta(hours=2)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no=service, from_name="Amsterdam", to_name="Berlin",
              depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    trip.itineraries = [Itinerary(fingerprint=title, depart_at=depart, arrive_at=arrive, duration_min=120,
                                  booked=booked, booked_price=price, booked_currency="EUR" if price else None,
                                  legs=[leg])]
    s.add(trip)
    s.commit()
    return trip.itineraries[0].id


def test_only_shows_the_one_journey_with_its_price(client, sessions):
    with sessions() as s:
        add(s, "First trip", SOON, price=Decimal("59.80"))
        second = add(s, "Second trip", SOON + timedelta(days=3), price=Decimal("242.75"), service="ICE 9")
    html = client.get(f"/upcoming?only={second}").text
    assert "Journey: Second trip" in html
    assert "First trip" not in html and "Paid €59.80" not in html
    assert "Paid €242.75" in html and "ICE 9" in html
    assert "<h2>Calendar</h2>" not in html
    assert 'href="/upcoming">All upcoming journeys</a>' in html


def test_only_an_unbooked_or_unknown_id_gives_404(client, sessions):
    with sessions() as s:
        unbooked = add(s, "Not booked trip", SOON, booked=False)
    assert client.get(f"/upcoming?only={unbooked}").status_code == 404
    assert client.get("/upcoming?only=999999").status_code == 404


def test_only_needs_the_login(sessions):
    r = TestClient(app).get("/upcoming?only=1", follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers["location"].endswith("/login")


def test_each_row_links_to_its_print_view(client, sessions):
    with sessions() as s:
        early = add(s, "Earlier trip", SOON)
        late = add(s, "Later trip", SOON + timedelta(days=3))
    html = client.get("/upcoming").text
    for it_id in (early, late):
        assert f'href="/upcoming?only={it_id}" aria-label="Print" title="Print"' in html
    assert "<h2>Calendar</h2>" in html
