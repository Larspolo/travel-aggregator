"""The whole feature of the epic "Travel per year CSV" (#1728): book, cancel with a refund in USD, then the page
and the file of 2026 agree (#1730)."""

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import CurrencyRate, Itinerary, Leg, Trip

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _journey(title, depart, mode, from_name, to_name, price, currency, **extra):
    arrive = depart + timedelta(hours=2)
    leg = Leg(seq=0, mode=mode, carrier="CX", service_no="1", from_name=from_name, to_name=to_name,
              depart_at=depart, depart_offset_min=0, arrive_at=arrive, arrive_offset_min=0)
    trip = Trip(title=title, origin_text="A", destination_text="B", status="planning")
    trip.itineraries = [Itinerary(fingerprint=title, depart_at=depart, arrive_at=arrive, duration_min=120,
                                  booked=True, booked_price=Decimal(price), booked_currency=currency, legs=[leg],
                                  **extra)]
    return trip


def _seed(sessions):
    with sessions() as s:
        s.add(CurrencyRate(code="USD", eur_per_unit=Decimal("0.8571"), updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        s.add(_journey("train", datetime(2026, 3, 10, 9, tzinfo=timezone.utc), "train", "Oslo", "Bergen",
                       "90.00", "EUR"))
        s.add(_journey("flight", datetime(2026, 5, 2, 9, tzinfo=timezone.utc), "flight", "Oslo", "Rome",
                       "100.00", "USD", cancelled_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                       refund_price=Decimal("40.00")))
        s.add(_journey("old", datetime(2025, 6, 1, 9, tzinfo=timezone.utc), "train", "Oslo", "Trondheim",
                       "20.00", "EUR"))
        s.commit()


def test_the_csv_file_agrees_with_the_paid_total_of_the_page(client, sessions):
    _seed(sessions)
    page = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", client.get("/upcoming/years").text))
    assert "1 journey · €141.43 paid · 2 h" in page  # 90.00 + (100 USD less 40 USD refund) at 0.8571

    link = re.search(r'href="(/upcoming/years/2026/export\.csv)" download', client.get("/upcoming/years").text)
    assert link is not None
    r = client.get(link.group(1))
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["date", "route", "modes", "carriers", "status", "paid", "currency", "paid_eur", "refund",
                       "refund_eur", "claim_paid"]
    journeys = rows[1:]
    assert [row[0] for row in journeys] == ["2026-03-10", "2026-05-02"]
    assert [row[4] for row in journeys] == ["booked", "cancelled"]

    paid = sum(Decimal(row[7] or 0) for row in journeys)
    refund = sum(Decimal(row[9] or 0) for row in journeys)
    assert paid - refund == Decimal("141.43")
