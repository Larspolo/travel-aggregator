"""The hour and transfer markups of the trip page come from query parameters (#14)."""

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def test_zero_markups_rank_by_price_only(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0").text
    assert "€89.90 price = €89.90" in page and "€150 price = €150" in page
    assert page.index("= €89.90") < page.index("= €150")
    default = client.get(f"/trips/{trip_id}").text
    assert default.index("= €210") < default.index("= €217.90")


def test_an_htmx_request_gets_only_the_rows(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    r = client.get(f"/trips/{trip_id}?hour_markup=30&transfer_markup=5", headers={"HX-Request": "true"})
    assert r.status_code == 200 and "<tr>" in r.text and "<html" not in r.text
    assert "€89.90 price + €236 time + €5 transfers = €330.90" in r.text


def test_a_value_outside_0_to_100_gives_422(trip):  # noqa: F811
    client, _, trip_id = trip
    for query in ("hour_markup=101", "hour_markup=-1", "transfer_markup=200", "hour_markup=abc"):
        assert client.get(f"/trips/{trip_id}?{query}").status_code == 422, query


def test_htmx_is_served_from_the_app(trip):  # noqa: F811
    client, _, _ = trip
    r = client.get("/static/htmx.min.js")
    assert r.status_code == 200 and "htmx" in r.text[:2000]
