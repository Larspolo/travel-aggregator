"""An expanded row of the trip table shows the legs, the transfer times and all fares with their links (#114)."""

from tests.test_ingest_api import BODY
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)
import copy


def post(client, auth, trip_id, source, price, url):
    body = copy.deepcopy(BODY)
    o = offer(price)
    o["booking_url"] = url
    body.update(trip_id=trip_id, source=source, offers=[o])
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def test_an_expanded_row_lists_legs_transfers_and_all_fares(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, "bahn.de", "89.90", "https://www.bahn.de/buchung/x")
    post(client, auth, trip_id, "sbb.ch", "95.00", None)
    page = client.get(f"/trips/{trip_id}").text
    details = page[page.index("<details><summary>Legs and fares"):]
    details = details[:details.index("</details>")]
    assert "DB ICE 105" in details and "<time>07:34</time> Amsterdam Centraal" in details and "<time>14:02</time> Basel SBB" in details
    assert "SBB IC 61" in details and "<time>15:26</time> Zürich HB" in details
    assert "Transfer at Basel SBB: 0h 31" in details
    assert "bahn.de: Sparpreis</span> <strong>€89.90" in details and "sbb.ch: Sparpreis</span> <strong>€95.00" in details
    assert details.count('href="https://www.bahn.de/buchung/x"') == 1 and details.count("<a ") == 1
