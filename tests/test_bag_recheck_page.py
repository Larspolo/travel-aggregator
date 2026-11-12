"""A leg with a bag recheck shows it in the expanded row of the trip page (#2662)."""
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def test_a_leg_with_a_bag_recheck_shows_the_recheck_at_its_origin(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][1]["bag_recheck"] = True
    origin = offer["legs"][1]["from_name"]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert f'<span class="badge recheck">collect the bags and check them in again at {origin}</span>' in page


def test_a_leg_without_a_bag_recheck_shows_no_recheck_badge(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][1]["bag_recheck"] = False
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert 'class="badge recheck"' not in page
    assert "check them in again" not in page
