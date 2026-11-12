"""The on-board services of a leg show in the expanded row of the trip page (#2550, #2548)."""
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def test_a_leg_with_wifi_and_power_shows_both_names(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["carrier"] = "FlixBus"
    offer["legs"][0]["services"] = ["wifi", "power"]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert '<span class="badge leg-services"' in page
    assert "Wi-Fi, power sockets" in page


def test_a_leg_with_only_power_shows_only_power_sockets(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["services"] = ["power"]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "power sockets" in page
    assert "Wi-Fi" not in page


def test_a_leg_without_services_shows_no_badge(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["services"] = []
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert 'class="badge leg-services"' not in page
