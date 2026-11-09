"""The navigation links to the Pinned page and shows the count of its offers (#1301)."""

import re
from datetime import datetime, timedelta, timezone

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


def add(s, title, status="planning", pinned=True):
    trip = Trip(title=title, origin_text="A", destination_text="B", status=status)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 1", from_name="Amsterdam", to_name="Berlin",
              depart_at=SOON, depart_offset_min=60, arrive_at=SOON + timedelta(hours=2), arrive_offset_min=60)
    trip.itineraries = [Itinerary(fingerprint=title, depart_at=SOON, arrive_at=SOON + timedelta(hours=2),
                                  duration_min=120, pinned=pinned, legs=[leg])]
    s.add(trip)
    s.commit()


def test_nav_shows_the_count_of_pinned_offers(client, sessions):
    with sessions() as s:
        for n in range(3):
            add(s, f"Planned {n}")
        add(s, "Archived", status="archived")
    html = client.get("/").text
    assert 'href="/pinned"' in html
    assert "Pinned (3)" in html


def test_nav_shows_only_pinned_with_no_pin(client):
    html = client.get("/").text
    assert 'href="/pinned"' in html
    assert ">Pinned<" in html
    assert "Pinned (" not in html
