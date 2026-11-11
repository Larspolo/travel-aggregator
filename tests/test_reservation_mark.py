"""The trip page marks a fare with a mandatory seat reservation that the price does not include (#1624)."""
import pytest  # noqa: F401

from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def test_a_fare_with_a_required_reservation_shows_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert post(client, auth, trip_id, [reserved("required", "included", None)])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert '<span class="badge reservation"' in page and "reservation required" in page


def test_a_fare_with_no_required_reservation_does_not_show_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert post(client, auth, trip_id, [reserved("included", "included", None)])["created"] == 1
    assert "reservation required" not in client.get(f"/trips/{trip_id}").text
