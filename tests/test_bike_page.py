"""A fare with a bicycle transport shows it in the expanded row of the trip page (#2456, #2461)."""
import pytest

from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

CASES = [
    ("allowed", "bicycle: allowed"),
    ("reservation", "bicycle: reservation"),
    ("no", "no bicycle"),
    (None, None),
]


@pytest.mark.parametrize("bike, mark", CASES)
def test_the_trip_page_shows_the_bicycle_transport(trip, bike, mark):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["bike"] = bike
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    if mark:
        assert '<span class="badge bike"' in page and mark in page
    else:
        assert 'class="badge bike"' not in page and "bicycle" not in page


def test_all_four_values_show_one_mark_each_and_no_mark_for_none(trip):  # noqa: F811
    client, auth, trip_id = trip
    offers = []
    for i, (bike, _) in enumerate(CASES):
        o = reserved(None, None, price=f"{80 + i}.90", fare=f"Fare {i}")
        o["bike"] = bike
        o["legs"][0]["service_no"] = f"ICE {100 + i}"
        offers.append(o)
    assert post(client, auth, trip_id, offers)["created"] == 4
    page = client.get(f"/trips/{trip_id}").text
    assert page.count('class="badge bike"') == 3
    for _, mark in CASES[:3]:
        assert mark in page
