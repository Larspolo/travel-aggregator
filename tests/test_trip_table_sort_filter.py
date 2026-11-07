"""The trip table sorts by each column header and filters by mode and source (#112)."""

import copy

from tests.test_ingest_api import BODY
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def bus(price):
    o = copy.deepcopy(direct(price))
    o["legs"][0].update(mode="bus", service_no="FLX 1", carrier="Flix")
    return o


def ingest_from(client, auth, trip_id, source, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=offers)
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def order(page, *marks):
    return [page.index(m) for m in marks]


def test_the_default_order_stays_by_effective_cost(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("= €210") < page.index("= €217.90")
    assert 'aria-sort="ascending"' in page and "sort=cost&amp;dir=desc" in page


def test_a_header_sorts_and_a_second_click_reverses(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}?sort=price&dir=asc").text
    assert page.index("= €217.90") < page.index("= €210")
    assert "sort=price&amp;dir=desc" in page  # the second click
    page = client.get(f"/trips/{trip_id}?sort=price&dir=desc").text
    assert page.index("= €210") < page.index("= €217.90")
    for key in ("route", "depart", "arrive", "carrier", "fare", "cost"):
        assert client.get(f"/trips/{trip_id}?sort={key}&dir=desc").status_code == 200, key
    assert client.get(f"/trips/{trip_id}?sort=bogus").status_code == 422


def test_the_header_links_keep_the_weights_and_filters(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    page = client.get(f"/trips/{trip_id}?hour_markup=30&mode=train").text
    assert "hour_markup=30" in page and "mode=train&amp;sort=price" in page.replace("source=&amp;", "")


def test_a_filter_by_mode_hides_the_other_rows(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), bus("20.00")])
    page = client.get(f"/trips/{trip_id}?mode=bus").text
    assert "FLX 1" in page and "ICE 105" not in page
    assert '<option value="train">' in page  # the other mode stays selectable
    rows = client.get(f"/trips/{trip_id}?mode=train", headers={"HX-Request": "true"}).text
    assert "ICE 105" in rows and "FLX 1" not in rows and "<html" not in rows


def test_a_filter_by_source_hides_the_other_rows(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    ingest_from(client, auth, trip_id, "flixbus.de", [bus("20.00")])
    page = client.get(f"/trips/{trip_id}?source=flixbus.de").text
    assert "FLX 1" in page and "ICE 105" not in page
    page = client.get(f"/trips/{trip_id}?source=nowhere").text
    assert "FLX 1" not in page and "ICE 105" not in page and 'name="source"' in page
