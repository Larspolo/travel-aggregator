"""The trip table filters by the earliest departure and the latest arrival, local time (#181)."""

import copy

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def timed(service, depart, arrive):
    """One leg with the given local times, each with its own offset."""
    o = copy.deepcopy(offer("89.90", service))
    o["legs"] = [dict(o["legs"][0], depart_at=depart, arrive_at=arrive)]
    return o


def test_earliest_departure_hides_an_earlier_offer_in_local_time(trip):  # noqa: F811
    client, auth, trip_id = trip
    # 06:30 at +01:00 is 05:30 UTC: before 07:00 local, although the UTC hour is 05
    ingest(client, auth, trip_id, [timed("EARLY 1", "2026-12-20T06:30:00+01:00", "2026-12-20T10:00:00+01:00"),
                                   timed("OK 2", "2026-12-20T07:30:00+01:00", "2026-12-20T11:00:00+01:00")])
    page = client.get(f"/trips/{trip_id}?earliest_depart=07:00").text
    assert "OK 2" in page and "EARLY 1" not in page
    assert 'value="07:00"' in page  # the box keeps its value
    rows = client.get(f"/trips/{trip_id}?earliest_depart=07:00", headers={"HX-Request": "true"}).text
    assert "OK 2" in rows and "EARLY 1" not in rows and "<html" not in rows


def test_latest_arrival_hides_a_late_and_a_next_day_offer(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("LATE 1", "2026-12-20T20:00:00+01:00", "2026-12-20T23:10:00+01:00"),
                                   timed("NIGHT 2", "2026-12-20T23:00:00+01:00", "2026-12-21T01:00:00+01:00"),
                                   timed("OK 3", "2026-12-20T18:00:00+01:00", "2026-12-20T21:30:00+01:00")])
    page = client.get(f"/trips/{trip_id}?latest_arrive=22:00").text
    assert "OK 3" in page and "LATE 1" not in page and "NIGHT 2" not in page
    assert 'name="latest_arrive"' in page and 'value="22:00"' in page


def test_the_time_filters_combine_and_an_empty_box_shows_all(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("EARLY 1", "2026-12-20T06:30:00+01:00", "2026-12-20T10:00:00+01:00"),
                                   timed("LATE 2", "2026-12-20T20:00:00+01:00", "2026-12-20T23:10:00+01:00"),
                                   timed("OK 3", "2026-12-20T09:00:00+01:00", "2026-12-20T21:30:00+01:00")])
    page = client.get(f"/trips/{trip_id}?earliest_depart=07:00&latest_arrive=22:00").text
    assert "OK 3" in page and "EARLY 1" not in page and "LATE 2" not in page
    page = client.get(f"/trips/{trip_id}?earliest_depart=&latest_arrive=").text
    assert "EARLY 1" in page and "LATE 2" in page and "OK 3" in page
    page = client.get(f"/trips/{trip_id}").text
    assert "EARLY 1" in page and "LATE 2" in page and "OK 3" in page


def test_the_header_links_keep_the_time_filters(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("OK 1", "2026-12-20T09:00:00+01:00", "2026-12-20T12:00:00+01:00")])
    page = client.get(f"/trips/{trip_id}?earliest_depart=07:00").text
    assert "earliest_depart=07%3A00&amp;sort=price" in page  # the sort links keep the filter


def test_a_bad_time_is_rejected(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert client.get(f"/trips/{trip_id}?earliest_depart=25:00").status_code == 422
    assert client.get(f"/trips/{trip_id}?latest_arrive=7pm").status_code == 422
