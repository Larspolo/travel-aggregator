"""A fare with 5 or fewer seats left shows "N seats left" on the trip page and the pinned page (#1827)."""
import pytest

from app.models import Fare
from tests.test_fare_reservations import reserved
from tests.test_pinned_page import SOON, add
from tests.test_pinned_page import client as pinned_client  # noqa: F401  (fixture)
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

CASES = [(2, "2 seats left"), (1, "1 seat left"), (6, None), (None, None)]


@pytest.mark.parametrize("seats, mark", CASES)
def test_the_trip_page_shows_the_seats_left(trip, seats, mark):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["seats_left"] = seats
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    if mark:
        assert '<span class="badge seats-left"' in page and mark in page
    else:
        assert "seats-left" not in page and "seat left" not in page


@pytest.mark.parametrize("seats, mark", CASES)
def test_the_pinned_page_shows_the_seats_left(pinned_client, sessions, seats, mark):  # noqa: F811
    with sessions() as s:
        add(s, "Trip", SOON)
        s.query(Fare).update({Fare.seats_left: seats})
        s.commit()
    page = pinned_client.get("/pinned").text
    if mark:
        assert mark in page
    else:
        assert "seats-left" not in page
