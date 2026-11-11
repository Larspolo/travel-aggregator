"""The row of an itinerary has the id it-<id>, so that a link can open it (#814)."""

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def test_the_row_of_each_itinerary_has_its_id_and_the_script_is_loaded(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 1"), offer("120.00", "ICE 2")])
    with sessions() as s:
        ids = [it.id for it in s.query(Itinerary).filter_by(trip_id=trip_id)]
    assert len(ids) == 2
    html = client.get(f"/trips/{trip_id}").text
    for it_id in ids:
        assert f'<tr id="it-{it_id}">' in html
    assert '<script src="/static/row_link.js" defer></script>' in html
    assert client.get("/static/row_link.js").status_code == 200
