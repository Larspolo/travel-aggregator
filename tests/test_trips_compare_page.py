"""GET /trips/compare (#2555): 2 to 4 trips side by side; the lowest best effective cost is marked."""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import require_login
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip

DEP = datetime(2026, 12, 20, 6, 0, tzinfo=UTC)
# the default profile adds €15 for the 1 h trip: price €82.40 gives effective €97.40, €97.00 gives €112.00


def add_trip(s, title, dest, price=None):
    trip = Trip(title=title, origin_text="Amsterdam", destination_text=dest, date_from=date(2026, 12, 20))
    s.add(trip)
    s.flush()
    if price:
        arr = DEP + timedelta(hours=1)
        it = Itinerary(trip_id=trip.id, fingerprint=f"fp{trip.id}", mode_summary="train", depart_at=DEP,
                       arrive_at=arr, duration_min=60, transfers=0)
        it.legs = [Leg(seq=0, mode="train", carrier="X", service_no="1", from_name="Amsterdam", to_name=dest,
                       depart_at=DEP, depart_offset_min=60, arrive_at=arr, arrive_offset_min=60)]
        it.fares = [Fare(source="src", latest_price=Decimal(price), currency="EUR", latest_captured_at=DEP)]
        s.add(it)
    s.commit()
    return trip.id


@pytest.fixture
def client():
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)


def test_two_trips_show_two_columns_and_mark_the_lowest_best_effective_cost(client, sessions):
    with sessions() as s:
        berlin = add_trip(s, "Amsterdam → Berlin", "Berlin", "82.40")
        paris = add_trip(s, "Amsterdam → Paris", "Paris", "97.00")
    page = client.get("/trips/compare", params={"id": [berlin, paris]})
    assert page.status_code == 200
    text = page.text
    assert "Amsterdam → Berlin" in text and "Amsterdam → Paris" in text
    assert re.search(r'class="cost best">effective €97\.40', text)
    assert re.search(r'class="cost">effective €112\.00', text)


def test_a_trip_with_no_offers_shows_no_offers_yet(client, sessions):
    with sessions() as s:
        a = add_trip(s, "Amsterdam → Berlin", "Berlin", "82.40")
        b = add_trip(s, "Empty", "Rome")
    text = client.get("/trips/compare", params={"id": [a, b]}).text
    assert "no offers yet" in text and 'class="cost best">effective €97.40' in text


@pytest.mark.parametrize("count", [1, 5])
def test_one_or_five_trips_show_the_reason(client, sessions, count):
    with sessions() as s:
        ids = [add_trip(s, f"T{n}", "Berlin") for n in range(count)]
    page = client.get("/trips/compare", params={"id": ids})
    assert page.status_code == 400 and "select 2 to 4 trips" in page.text.lower()


def test_an_unknown_id_gives_404(client, sessions):
    with sessions() as s:
        a = add_trip(s, "A", "Berlin")
    assert client.get("/trips/compare", params={"id": [a, 999999]}).status_code == 404


def test_the_trips_list_has_a_checkbox_per_trip_and_the_compare_button(client, sessions):
    with sessions() as s:
        a = add_trip(s, "A", "Berlin")
    text = client.get("/").text
    assert 'action="/trips/compare"' in text and "Compare trips" in text
    assert f'name="id" value="{a}" form="trips-compare"' in text
