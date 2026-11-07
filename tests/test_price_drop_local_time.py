"""The box "Price drops" of the trip page shows the local departure time of the offer, in the same format as the table
(#448). The stored offset of the first leg decides the local time."""

from tests.test_price_drops import _pin, _token
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def test_the_drop_box_shows_the_local_departure_time(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    _pin(client, sessions, trip_id, "ICE 105", _token(client, trip_id))
    client.get(f"/trips/{trip_id}")  # the view stores the seen price
    ingest(client, auth, trip_id, [offer("79.90", "ICE 105")])
    page = client.get(f"/trips/{trip_id}").text
    box = page.split('id="drops"', 1)[1].split("</section>", 1)[0]
    assert "Sun 20 Dec 07:34" in box  # the table's format and the original offset (+01:00)
    assert "06:34" not in box  # not the UTC time
    assert "Sun 20 Dec 07:34" in page.split('id="table"', 1)[1]
