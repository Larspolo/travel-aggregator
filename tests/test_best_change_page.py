"""The days on which the best offer changed, in the "Price trend" card of the trip page (#2166)."""

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import profiles
from app.auth import require_login
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Leg, Trip
from app.ranking import Weights

LINE = re.compile(r'<li>5 Nov: <a href="#it-(\d+)">ICE 105</a> \(effective €[\d.]+\) is best, '
                  r'was <a href="#it-(\d+)">Flixbus N 801</a> \(effective €[\d.]+\)</li>')


def _at(day, hour=12):
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def _offer(s, trip, n, carrier, service, hours):
    it = Itinerary(trip=trip, fingerprint=f"fp{n}", depart_at=_at(20, 6), arrive_at=_at(20, 6 + hours),
                   duration_min=hours * 60, mode_summary="train")
    it.legs = [Leg(seq=0, mode="train", carrier=carrier, service_no=service, from_name="Amsterdam", to_name="Berlin",
                   depart_at=_at(20, 6), depart_offset_min=60, arrive_at=_at(20, 6 + hours), arrive_offset_min=60)]
    fare = Fare(itinerary=it, source="test", latest_price=Decimal("1"), currency="EUR", latest_captured_at=_at(5))
    s.add_all([it, fare])
    s.flush()
    return it, fare


def _price(s, fare, amount, day):
    fare.latest_price = Decimal(amount)
    s.add(FarePrice(fare=fare, price=Decimal(amount), currency="EUR", captured_at=_at(day)))


@pytest.fixture
def client():
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)


def _trip(sessions, train_day5="40.00"):
    with sessions() as s:
        trip = Trip(title="Changes")
        s.add(trip)
        s.flush()
        ice, ice_fare = _offer(s, trip, 1, "ICE", "105", 4)
        bus, bus_fare = _offer(s, trip, 2, "Flixbus", "N 801", 4)
        _price(s, bus_fare, "50.00", 3)
        _price(s, ice_fare, "90.00", 3)
        _price(s, ice_fare, train_day5, 5)
        s.commit()
        return trip.id, ice.id, bus.id


def test_a_change_of_the_best_offer_is_one_line_with_two_links(sessions, client):
    trip_id, ice, bus = _trip(sessions)
    page = client.get(f"/trips/{trip_id}").text
    assert "Best offer changes" in page
    match = LINE.search(page)
    assert match and match.groups() == (str(ice), str(bus))
    assert f'id="it-{ice}"' in page and f'id="it-{bus}"' in page


def test_no_change_gives_no_list(sessions, client):
    trip_id, _, _ = _trip(sessions, train_day5="80.00")
    page = client.get(f"/trips/{trip_id}").text
    assert "Price trend" in page and "Best offer changes" not in page


def test_the_page_of_another_profile_shows_the_list_of_that_profile(sessions, client):
    trip_id, _, bus = _trip(sessions)
    with sessions() as s:
        s.get(Itinerary, bus).duration_min = 9 * 60  # the bus is slow: a high hour value makes the ICE best each day
        cheap = profiles.save(s, "time is cheap", Weights(hour_markup=Decimal("0"))).id
        dear = profiles.save(s, "time is dear", Weights(hour_markup=Decimal("100"))).id
        s.commit()
    assert LINE.search(client.get(f"/trips/{trip_id}?profile={cheap}").text)
    assert "Best offer changes" not in client.get(f"/trips/{trip_id}?profile={dear}").text
