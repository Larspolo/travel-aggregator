"""The flags, the paid price and the pages of the target trip after a merge (#1287, part of #1260)."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, DayPrice, Fare, FarePrice, Itinerary, Leg, Trip
from app.trip_merge import merge_trips

PASSWORD = "correct horse"


def _at(day, hour=10):
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def _it(s, trip, fp, prices, source="stub", fare_name="Flex", **flags):
    it = Itinerary(trip_id=trip.id, fingerprint=fp, depart_at=_at(20, 8), arrive_at=_at(20, 11), duration_min=180,
                   first_seen_at=flags.pop("first", _at(1)), last_seen_at=_at(1), **flags)
    fare = Fare(source=source, fare_name=fare_name, latest_price=Decimal(prices[-1][0]), currency="EUR",
                latest_captured_at=_at(prices[-1][1]))
    fare.prices = [FarePrice(price=Decimal(p), currency="EUR", captured_at=_at(d)) for p, d in prices]
    it.fares.append(fare)
    s.add(it)
    return it


def _pair(s, source_kwargs, target_kwargs):
    """A source and a target trip, each with one itinerary of the same journey ("x")."""
    a = Trip(title="Source", origin_text="Köln", destination_text="Basel")
    b = Trip(title="Target", origin_text="Wien", destination_text="Graz",
             date_from=date(2026, 11, 30), date_to=date(2026, 12, 2))
    s.add_all([a, b])
    s.flush()
    _it(s, a, "x", [("50.00", 1)], **source_kwargs)
    _it(s, b, "x", [("60.00", 1)], **target_kwargs)
    s.commit()
    return a.id, b.id


def _joined(s, trip_id):
    return s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.fingerprint == "x")).one()


def test_a_joined_itinerary_keeps_the_hidden_mark_of_the_source(sessions):
    with sessions() as s:
        a, b = _pair(s, {"hidden": True}, {})
        merge_trips(s, a, b)
    with sessions() as s:
        assert _joined(s, b).hidden is True


def test_a_joined_itinerary_takes_the_paid_price_of_the_source_when_the_target_has_none(sessions):
    with sessions() as s:
        a, b = _pair(s, {"booked": True, "booked_price": Decimal("80.00"), "booked_currency": "EUR",
                         "booked_at": _at(5)}, {})
        merge_trips(s, a, b)
    with sessions() as s:
        it = _joined(s, b)
        assert it.booked is True
        assert it.booked_price == Decimal("80.00")
        assert it.booked_currency == "EUR"
        assert it.booked_at == _at(5)


def test_a_joined_itinerary_keeps_its_own_paid_price(sessions):
    with sessions() as s:
        a, b = _pair(s, {"booked": True, "booked_price": Decimal("80.00"), "booked_currency": "EUR",
                         "booked_at": _at(5)},
                     {"booked": True, "booked_price": Decimal("65.00"), "booked_currency": "EUR",
                      "booked_at": _at(6)})
        merge_trips(s, a, b)
    with sessions() as s:
        it = _joined(s, b)
        assert it.booked_price == Decimal("65.00")
        assert it.booked_at == _at(6)


@pytest.fixture
def trips(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        a = Trip(title="Source", origin_text="Köln", destination_text="Basel")
        c = Trip(title="Target", origin_text="Wien", destination_text="Graz",
                 date_from=date(2026, 11, 30), date_to=date(2026, 12, 2))
        s.add_all([a, c])
        s.flush()
        it = _it(s, a, "a0", [("10.00", 1)])
        it.legs.append(Leg(seq=0, mode="train", from_name="Köln", to_name="Basel", depart_at=_at(20, 8),
                           depart_offset_min=60, arrive_at=_at(20, 11), arrive_offset_min=60))
        cap = Capture(trip_id=a.id, source="stub", captured_at=_at(3))
        s.add(cap)
        s.add(DayPrice(source="stub", trip_id=a.id, day=date(2026, 12, 1), price=Decimal("5"), currency="EUR",
                       captured_at=_at(3)))
        s.commit()
        return {"source": a.id, "target": c.id, "capture_time": _at(3).isoformat()}


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def test_after_the_merge_the_source_is_gone_and_the_target_pages_show_its_data(trips):
    client = TestClient(app)
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client, "/login")},
                    follow_redirects=False)
    assert r.status_code == 303
    target, source = trips["target"], trips["source"]
    csrf = _csrf(client, f"/trips/{source}/edit")
    r = client.post(f"/trips/{source}/merge?into={target}", data={"csrf_token": csrf, "into": target},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{target}"

    assert client.get(f"/trips/{source}").status_code == 404

    captures = client.get(f"/trips/{target}/captures")
    assert captures.status_code == 200
    assert f'datetime="{trips["capture_time"]}"' in captures.text

    page = client.get(f"/trips/{target}")
    assert page.status_code == 200
    assert "(stub day price)" in page.text
