"""The end date of the share link on the trip page (#2027)."""

from datetime import datetime, timedelta, timezone

from app.models import Trip
from tests.test_share import _setup, share
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def _today():
    return datetime.now(timezone.utc).date()


def _set_end(sessions, trip_id, day):
    with sessions() as s:
        s.get(Trip, trip_id).share_ends_on = day
        s.commit()


def test_the_trip_page_shows_the_end_of_the_link(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    share(client, trip_id)
    next_week = _today() + timedelta(days=7)
    _set_end(sessions, trip_id, next_week)
    assert f"Ends on {next_week.isoformat()}" in client.get(f"/trips/{trip_id}").text
    _set_end(sessions, trip_id, _today() - timedelta(days=1))
    page = client.get(f"/trips/{trip_id}").text
    assert "Link ended on" in page and "Ends on" not in page
    _set_end(sessions, trip_id, None)
    page = client.get(f"/trips/{trip_id}").text
    assert "share-ends" not in page and "ended" not in page


def test_the_end_date_field_has_a_label_and_posts_to_the_end_route(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    share(client, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert '<label for="f-share-end">End date</label>' in page
    assert '<input id="f-share-end" type="date" name="share_ends_on"' in page
    assert f'action="/trips/{trip_id}/share/end"' in page
