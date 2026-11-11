"""The trip table filters by the local day of the departure (#709)."""

import copy

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def timed(service, depart, arrive):
    """One leg with the given local times, each with its own offset."""
    o = copy.deepcopy(offer("89.90", service))
    o["legs"] = [dict(o["legs"][0], depart_at=depart, arrive_at=arrive)]
    return o


def test_the_day_shows_only_the_offers_that_depart_that_local_day(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("DAY 1", "2026-12-18T09:00:00+01:00", "2026-12-18T12:00:00+01:00"),
                                   timed("NEXT 2", "2026-12-19T09:00:00+01:00", "2026-12-19T12:00:00+01:00")])
    page = client.get(f"/trips/{trip_id}?day=2026-12-18").text
    assert "DAY 1" in page and "NEXT 2" not in page
    page = client.get(f"/trips/{trip_id}").text
    assert "DAY 1" in page and "NEXT 2" in page  # with no day, all offers


def test_an_offer_late_in_the_evening_stays_on_its_local_day(trip):  # noqa: F811
    client, auth, trip_id = trip
    # 23:30 at +01:00 is 22:30 UTC: the local day is 18 December, not 19 December
    ingest(client, auth, trip_id, [timed("EVENING 1", "2026-12-18T23:30:00+01:00", "2026-12-19T02:00:00+01:00")])
    assert "EVENING 1" in client.get(f"/trips/{trip_id}?day=2026-12-18").text
    assert "EVENING 1" not in client.get(f"/trips/{trip_id}?day=2026-12-19").text


def test_the_day_is_kept_by_the_sort_links_and_the_slider_form(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("DAY 1", "2026-12-18T09:00:00+01:00", "2026-12-18T12:00:00+01:00")])
    page = client.get(f"/trips/{trip_id}?day=2026-12-18").text
    assert "day=2026-12-18" in page  # the sort links keep it
    assert 'name="day" value="2026-12-18"' in page  # a slider change keeps it
    rows = client.get(f"/trips/{trip_id}?day=2026-12-18", headers={"HX-Request": "true"}).text
    assert "DAY 1" in rows and "<html" not in rows


def test_a_bad_day_is_rejected(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert client.get(f"/trips/{trip_id}?day=18.12.2026").status_code == 422
