"""The Upcoming page shows the paid price of each journey and the total paid in EUR (#1149)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import CurrencyRate, Itinerary, Leg, Trip

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=10)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(s, title, price=None, currency=None, days=0):
    depart = SOON + timedelta(days=days)
    arrive = depart + timedelta(hours=2)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 1", from_name="A", to_name="B",
              depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    trip = Trip(title=title, origin_text="A", destination_text="B", status="planning")
    trip.itineraries = [Itinerary(fingerprint=title, depart_at=depart, arrive_at=arrive, duration_min=120, booked=True,
                                  booked_price=price, booked_currency=currency, legs=[leg])]
    s.add(trip)
    s.commit()


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_two_journeys_show_their_prices_and_the_total(client, sessions):
    with sessions() as s:
        add(s, "One", Decimal("59.80"), "EUR")
        add(s, "Two", Decimal("242.75"), "EUR", days=1)
        add(s, "Unpaid", days=2)
    t = text(client.get("/upcoming").text)
    assert "Paid €59.80" in t and "Paid €242.75" in t
    assert "Total paid: €302.55" in t
    assert t.count("Paid €") == 2


def test_a_price_in_chf_with_a_rate_counts_in_eur(client, sessions):
    with sessions() as s:
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("1.05"), updated_at=datetime.now(timezone.utc)))
        add(s, "Swiss", Decimal("120"), "CHF")
        add(s, "Dutch", Decimal("10.00"), "EUR", days=1)
    t = text(client.get("/upcoming").text)
    assert "Paid CHF 120.00" in t and "Total paid: €136.00" in t and "no rate" not in t


def test_a_price_with_no_rate_is_left_out_and_named(client, sessions):
    with sessions() as s:
        add(s, "Swiss", Decimal("120"), "CHF")
        add(s, "Dutch", Decimal("10.00"), "EUR", days=1)
    t = text(client.get("/upcoming").text)
    assert "Paid CHF 120.00" in t
    assert "Total paid: €10.00 (1 price in CHF has no rate)" in t


def test_no_paid_price_shows_no_total(client, sessions):
    with sessions() as s:
        add(s, "Unpaid")
    assert "Total paid" not in client.get("/upcoming").text
