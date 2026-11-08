"""The trips list marks a trip that has an active share link (#905, epic #903)."""

from tests.test_share import _csrf, share
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

MARK = '<span class="drop">shared</span>'


def test_a_shared_trip_is_marked_on_the_trips_list_until_revoked(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert MARK not in client.get("/").text

    share(client, trip_id)
    assert MARK in client.get("/").text

    r = client.post(f"/trips/{trip_id}/share/revoke", data={"csrf_token": _csrf(client, trip_id)})
    assert r.status_code in (200, 303)
    assert MARK not in client.get("/").text
