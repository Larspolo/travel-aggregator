"""The "only these" filter of the trip table (#1857): with `pareto=true` the table shows only the offers with the mark
"no faster offer for less" (#1856), the sort links keep the filter, and the form shows its state."""

from tests.test_stale_filter import _two_offers
from tests.test_stale_flag import _row
from tests.test_trip_page import trip  # noqa: F401 (fixture)


def test_only_these_hides_the_offers_without_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two_offers(client, auth, trip_id)
    # the cheaper offer has the mark; the dearer one, with the same times, has none
    page = client.get(f"/trips/{trip_id}").text
    assert "DB ICE 105" in page and "DB ICE 123" in page
    assert "no faster offer for less" in _row(page, "ICE 105")
    assert "no faster offer for less" not in _row(page, "ICE 123")
    page = client.get(f"/trips/{trip_id}", params={"pareto": "true"}).text
    assert "DB ICE 105" in page and "DB ICE 123" not in page
    assert 'name="pareto" value="true" checked' in page


def test_the_filter_is_off_by_default(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two_offers(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert 'name="pareto" value="true" checked' not in page
    assert "pareto=True" not in page


def test_a_sort_link_keeps_only_these(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two_offers(client, auth, trip_id)
    assert "pareto=True" in client.get(f"/trips/{trip_id}", params={"pareto": "true"}).text
