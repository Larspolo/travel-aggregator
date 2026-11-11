"""A fare with no bicycle value shows "bicycle: not known" on a bicycle trip only (#2476)."""
import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post


@pytest.fixture
def make_trip(sessions):
    """A client with the owner login, a token and a trip; bike sets "With a bicycle" on the trip."""

    def make(bike):
        with sessions() as s:
            token = tokens.create(s, "test")
            t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich", bike=bike)
            s.add(t)
            s.commit()
            trip_id = t.id
        app.dependency_overrides[require_login] = lambda: None
        return TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id

    yield make
    app.dependency_overrides.pop(require_login, None)


def test_on_a_bicycle_trip_an_unknown_fare_says_not_known_and_a_reservation_says_so(make_trip):
    client, auth, trip_id = make_trip(True)
    unknown = reserved(None, None, price="80.90", fare="Fare unknown")
    unknown["bike"] = None
    reservation = reserved(None, None, price="81.90", fare="Fare reservation")
    reservation["bike"] = "reservation"
    reservation["legs"][0]["service_no"] = "ICE 101"
    unknown["legs"][0]["service_no"] = "ICE 100"
    assert post(client, auth, trip_id, [unknown, reservation])["created"] == 2
    page = client.get(f"/trips/{trip_id}").text
    assert '<span class="badge bike" title="the capture tells nothing about a bicycle">bicycle: not known</span>' in page
    assert "bicycle: reservation" in page


def test_on_a_trip_with_no_bicycle_an_unknown_fare_shows_no_bicycle_badge(make_trip):
    client, auth, trip_id = make_trip(False)
    unknown = reserved(None, None, price="80.90", fare="Fare unknown")
    unknown["bike"] = None
    assert post(client, auth, trip_id, [unknown])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert 'class="badge bike"' not in page
    assert "bicycle" not in page
