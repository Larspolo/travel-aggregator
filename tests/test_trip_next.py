"""Add next trip (#560): a new trip starts at the destination of the last trip of the journey."""

from sqlalchemy import select

from app.models import Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)


def _set_places(sessions, trip_id, origin, destination):
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        trip.origin_text, trip.destination_text = origin, destination
        s.commit()


def _next(c, trip_id):
    r = c.post(f"/trips/{trip_id}/next", headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)
    assert r.status_code == 303
    return int(r.headers["location"].split("/")[2])


def _row(sessions, trip_id):
    with sessions() as s:
        t = s.get(Trip, trip_id)
        return t.origin_text, t.destination_text, t.return_of_id, t.title


def test_three_next_trips_make_a_chain_of_four(setup, sessions):  # noqa: F811
    c, _, first = setup
    _set_places(sessions, first, "Köln", "München")
    ids = [first]
    for city in ("Salzburg", "Wien", "Budapest"):
        new = _next(c, first)  # always posted on the first trip: the new trip still goes to the end
        ids.append(new)
        _set_places(sessions, new, _row(sessions, new)[0], city)
    rows = [_row(sessions, i) for i in ids[1:]]
    assert [r[2] for r in rows] == ids[:-1]  # each new trip points to the trip before it
    assert [r[0] for r in rows] == ["München", "Salzburg", "Wien"]  # each starts where the last one ends
    assert rows[-1][3].endswith("(part 4)")


def test_a_next_trip_from_a_middle_trip_is_added_at_the_end(setup, sessions):  # noqa: F811
    c, _, first = setup
    _set_places(sessions, first, "Köln", "München")
    second = _next(c, first)
    _set_places(sessions, second, "München", "Salzburg")
    third = _next(c, first)
    _set_places(sessions, third, "Salzburg", "Wien")
    new = _next(c, second)  # second is the middle of three trips
    assert _row(sessions, new)[2] == third
    assert _row(sessions, new)[0] == "Wien"


def test_a_request_without_the_csrf_token_is_refused(setup, sessions):  # noqa: F811
    c, _, first = setup
    assert c.post(f"/trips/{first}/next", follow_redirects=False).status_code == 403
    with sessions() as s:
        assert s.scalar(select(Trip).where(Trip.return_of_id == first)) is None
