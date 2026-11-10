"""The page "Travel per year" lists the open delay claims, and "Claim paid" marks one as done (#1693)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip

PASSWORD = "pw"
PAST = datetime(2026, 3, 1, 8, tzinfo=timezone.utc)
PAGE = "/upcoming/years"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(sessions, delay, mode="train", paid=None, title="Utrecht trip", day=0):
    depart = PAST + timedelta(days=day)
    leg = Leg(seq=0, mode=mode, carrier="NS", service_no="1", from_name="A", to_name="B", depart_at=depart,
              depart_offset_min=60, arrive_at=depart + timedelta(hours=2), arrive_offset_min=60)
    trip = Trip(title=title, origin_text="A", destination_text="B", status="planning")
    it = Itinerary(fingerprint=title, depart_at=depart, arrive_at=depart + timedelta(hours=2), duration_min=120,
                   booked=True, booked_price=Decimal("90"), booked_currency="EUR", delay_min=delay,
                   claim_paid_at=paid, legs=[leg])
    trip.itineraries = [it]
    with sessions() as s:
        s.add(trip)
        s.commit()
        return trip.id, it.id


def section(html):
    return html.split("Open claims", 1)[1].split("</section>", 1)[0]


def toggle(client, iid):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/login").text).group(1)
    return client.post(f"{PAGE}/claims/{iid}/paid", data={"csrf_token": token}, follow_redirects=False)


def test_an_open_claim_is_listed_with_a_link_to_its_trip(client, sessions):
    tid, _ = add(sessions, 75)
    part = section(client.get(PAGE).text)
    assert "Claim €22.50 (25 %)" in part and f'href="/trips/{tid}"' in part and "2026-03-01" in part


def test_claim_paid_removes_it_and_a_second_post_shows_it_again(client, sessions):
    _, iid = add(sessions, 75)
    r = toggle(client, iid)
    assert r.status_code == 303 and r.headers["location"] == PAGE
    assert "No open claims" in section(client.get(PAGE).text)
    toggle(client, iid)
    assert "Claim €22.50" in section(client.get(PAGE).text)


def test_no_claim_or_a_paid_claim_is_not_listed(client, sessions):
    add(sessions, 40, title="a")
    add(sessions, 75, mode="bus", title="b")
    add(sessions, 75, paid=PAST, title="c")
    add(sessions, None, title="d")
    assert "No open claims" in section(client.get(PAGE).text)


def test_the_newest_claim_is_first(client, sessions):
    add(sessions, 75, title="old", day=0)
    add(sessions, 130, title="new", day=5)
    part = section(client.get(PAGE).text)
    assert part.index("€45.00") < part.index("€22.50")


def test_an_unknown_itinerary_is_404(client, sessions):
    assert toggle(client, 999).status_code == 404
