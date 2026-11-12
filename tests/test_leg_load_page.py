"""The expected load of a leg shows in the expanded row of the trip page (#2583, #2599)."""
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def test_a_leg_with_both_loads_shows_both_classes(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["load_first"] = 3
    offer["legs"][0]["load_second"] = 3
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert '<span class="badge leg-load">' in page
    assert "expected load: 1st class very high, 2nd class very high" in page


def test_a_leg_with_only_second_class_load_shows_only_second_class(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["load_second"] = 4
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "expected load: 2nd class fully booked</span>" in page
    assert "expected load: 1st" not in page


def test_a_leg_without_loads_shows_no_load_badge(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert 'class="badge leg-load"' not in page
