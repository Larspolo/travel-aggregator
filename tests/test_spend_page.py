"""The page "Travel per year" shows the booked journeys per year and per mode (#1364)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(s, n, year, mode, minutes, price, booked=True):
    depart = datetime(year, 3, 1 + n, 8, tzinfo=timezone.utc)
    arrive = depart + timedelta(minutes=minutes)
    leg = Leg(seq=0, mode=mode, carrier="X", service_no="1", from_name="A", to_name="B",
              depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    trip = Trip(title=f"T{year}-{n}", origin_text="A", destination_text="B", status="planning")
    trip.itineraries = [Itinerary(fingerprint=f"f{year}-{n}", depart_at=depart, arrive_at=arrive, duration_min=minutes,
                                  booked=booked, booked_price=Decimal(price), booked_currency="EUR", legs=[leg])]
    s.add(trip)


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_years_and_modes(client, sessions):
    with sessions() as s:
        rows = [("train", 600, "100.00"), ("train", 600, "100.00"), ("train", 600, "100.00"),
                ("bus", 480, "40.00"), ("bus", 480, "40.00"), ("flight", 450, "131.25"), ("flight", 450, "131.25")]
        for n, (mode, minutes, price) in enumerate(rows):
            add(s, n, 2026, mode, minutes, price)
        add(s, 0, 2025, "train", 120, "20.00")
        add(s, 9, 2026, "train", 600, "999.00", booked=False)
        s.commit()
    page = text(client.get("/upcoming/years").text)
    assert "7 journeys · €642.50 paid · 61 h" in page
    assert "Train: 3 journeys" in page and "Bus: 2 journeys" in page and "Flight: 2 journeys" in page
    assert "1 journey · €20.00 paid · 2 h" in page
    assert page.index("2026") < page.index(" 2025 ")


def test_no_journeys(client):
    assert "No booked journeys." in client.get("/upcoming/years").text


def test_login_and_link(client):
    assert 'href="/upcoming/years"' in client.get("/upcoming").text
    r = TestClient(app).get("/upcoming/years", follow_redirects=False)
    assert r.status_code in (302, 303, 401)
