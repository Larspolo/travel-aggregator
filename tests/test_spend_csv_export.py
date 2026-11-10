"""The route "Export CSV" of one year of "Travel per year" (#1730): the file, its header and its cells."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip

PASSWORD = "pw"
HEADER = "date,route,modes,carriers,status,paid,currency,paid_eur,refund,refund_eur,claim_paid"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _add(s, depart, carrier, price, currency="EUR", booked=True, cancelled_at=None, refund=None):
    arrive = depart + timedelta(hours=1)
    leg = Leg(seq=0, mode="train", carrier=carrier, service_no="1", from_name="Oslo", to_name="Bergen",
              depart_at=depart, depart_offset_min=0, arrive_at=arrive, arrive_offset_min=0)
    trip = Trip(title=f"T{carrier}{depart:%Y%m%d}", origin_text="A", destination_text="B", status="planning")
    trip.itineraries = [Itinerary(fingerprint=f"f{carrier}{depart:%Y%m%d}", depart_at=depart, arrive_at=arrive,
                                  duration_min=60, booked=booked, booked_price=Decimal(price),
                                  booked_currency=currency, cancelled_at=cancelled_at, refund_price=refund,
                                  legs=[leg])]
    s.add(trip)


def test_the_file_has_the_header_and_one_row_per_journey_of_the_year(client, sessions):
    with sessions() as s:
        _add(s, datetime(2026, 3, 1, 9, tzinfo=timezone.utc), "NS", "90.00")
        _add(s, datetime(2025, 12, 31, 9, tzinfo=timezone.utc), "SJ", "20.00")
        s.commit()
    r = client.get("/upcoming/years/2026/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="travel-2026.csv"'
    body = r.content.decode("utf-8")
    assert body.startswith("﻿" + HEADER + "\r\n")
    lines = body.lstrip("﻿").splitlines()
    assert lines == [HEADER, "2026-03-01,Oslo - Bergen,train,NS,booked,90.00,EUR,90.00,,,"]


def test_a_year_with_no_journey_gives_the_header_only(client):
    body = client.get("/upcoming/years/1999/export.csv").content.decode("utf-8")
    assert body.lstrip("﻿").splitlines() == [HEADER]


def test_a_carrier_that_starts_like_a_formula_is_quoted(client, sessions):
    with sessions() as s:
        _add(s, datetime(2026, 4, 1, 9, tzinfo=timezone.utc), "=SUM(A1)", "10.00")
        s.commit()
    body = client.get("/upcoming/years/2026/export.csv").content.decode("utf-8")
    assert ",'=SUM(A1)," in body  # the cell gets a leading apostrophe (CSV injection)


def test_no_login_goes_to_the_login_page():
    r = TestClient(app).get("/upcoming/years/2026/export.csv", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers["location"]
