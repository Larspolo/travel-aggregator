"""The price change of each fare since the last view of the trip page (#1092)."""

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _view(client, auth, trip_id, first, then):
    ingest(client, auth, trip_id, [offer(first)])
    client.get(f"/trips/{trip_id}")  # the view stores the seen price
    ingest(client, auth, trip_id, [offer(then)])
    return client.get(f"/trips/{trip_id}").text


def test_a_drop_shows_the_old_and_the_new_price(trip):  # noqa: F811
    client, auth, trip_id = trip
    page = _view(client, auth, trip_id, "95.00", "90.00")
    assert page.count("€95.00 → €90.00") == 2  # the main row and the fares of the expanded row
    assert 'price-change down' in page


def test_a_rise_shows_the_old_and_the_new_price(trip):  # noqa: F811
    client, auth, trip_id = trip
    page = _view(client, auth, trip_id, "90.00", "99.00")
    assert "€90.00 → €99.00" in page and 'price-change up' in page


def test_no_change_for_the_same_price_a_new_fare_and_a_second_view(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("95.00")])
    assert "→ €" not in client.get(f"/trips/{trip_id}").text  # a new fare: no seen price
    assert "→ €" not in _view(client, auth, trip_id, "95.00", "95.00")
    ingest(client, auth, trip_id, [offer("90.00")])
    assert "€95.00 → €90.00" in client.get(f"/trips/{trip_id}").text
    assert "→ €" not in client.get(f"/trips/{trip_id}").text  # the second view
