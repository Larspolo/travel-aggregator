"""The whole "new since the last view" feature of a trip (#1101): the "N new" count of the trips list (#1091), the "new"
mark of the rows (#1090) and the price change of a fare (#1092) work together. An htmx re-rank keeps the changes."""

import re

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

NEW_MARK = 'class="badge new"'
PRICE_CHANGE = re.compile(r'class="price-change down"[^>]*>[^<]*95[^<]*→[^<]*90')


def _changes(client, trip_id):
    """The trips list and then the trip page: the full view of the page marks the trip as viewed (after the list)."""
    listing = client.get("/").text
    page = client.get(f"/trips/{trip_id}").text
    return ("2 new" in listing, page.count(NEW_MARK), bool(PRICE_CHANGE.search(page)))


def test_new_since_the_last_view_works_as_a_whole(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("95.00", "ICE 105")])
    client.get(f"/trips/{trip_id}")  # the first full view: the trip is viewed, the fare price 95 is seen

    ingest(client, auth, trip_id, [offer("90.00", "ICE 105"), offer("80.00", "ICE 201"), offer("79.00", "ICE 303")])

    # The list shows the count without a view; an htmx re-rank does not mark the trip as viewed either.
    assert "2 new" in client.get("/").text
    client.get(f"/trips/{trip_id}", headers={"HX-Request": "true"})
    assert "2 new" in client.get("/").text

    # The first full view still shows the 3 changes: 2 new rows and the price change of the fare.
    assert _changes(client, trip_id) == (True, 2, True)

    # A second full view shows none of them.
    assert _changes(client, trip_id) == (False, 0, False)
