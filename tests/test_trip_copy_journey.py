"""Copy journey (#802): the copies of a journey, linked in the same order."""

from app.models import Itinerary, Trip
from app.trips import chain, in_journeys, list_trips
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_page import ingest, offer


def _journey(sessions, trip_id):
    """A journey of 3 trips: the fixture trip, then 2 linked trips, with places and one offer."""
    with sessions() as s:
        first = s.get(Trip, trip_id)
        first.origin_text, first.destination_text, first.notes = "Köln", "München", "Bahncard 50"
        second = Trip(title="München – Wien", origin_text="München", destination_text="Wien", return_of_id=trip_id)
        s.add(second)
        s.flush()
        third = Trip(title="Wien – Köln", origin_text="Wien", destination_text="Köln", return_of_id=second.id)
        s.add(third)
        s.commit()
        return [first.id, second.id, third.id]


def _post(c, path):
    return c.post(path, headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)


def _copies(sessions):
    with sessions() as s:
        return s.query(Trip).filter(Trip.title.like("%(copy)")).order_by(Trip.id).all()


def test_the_copy_journey_has_the_same_order_and_links(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _journey(sessions, trip_id)
    r = _post(c, f"/trips/{trip_id}/copy-journey")
    assert r.status_code == 303
    first, second, third = _copies(sessions)
    assert r.headers["location"] == f"/trips/{first.id}/edit"
    assert first.return_of_id is None
    assert second.return_of_id == first.id and third.return_of_id == second.id
    assert (first.origin_text, first.destination_text, first.notes) == ("Köln", "München", "Bahncard 50")
    assert (second.origin_text, third.destination_text) == ("München", "Köln")
    assert first.date_from is None and second.date_from is None and third.date_from is None
    with sessions() as s:
        assert s.query(Itinerary).filter(Itinerary.trip_id.in_([first.id, second.id, third.id])).count() == 0
        assert len(chain(s.get(Trip, first.id))) == 3


def test_the_copies_show_as_one_journey_and_the_original_is_not_changed(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    ids = _journey(sessions, trip_id)
    ingest(c, auth, trip_id, [offer("89.90")])
    with sessions() as s:
        before = [(t.title, t.return_of_id) for t in (s.get(Trip, i) for i in ids)]
    _post(c, f"/trips/{trip_id}/copy-journey")
    with sessions() as s:
        assert [(t.title, t.return_of_id) for t in (s.get(Trip, i) for i in ids)] == before
        lines = in_journeys(list_trips(s))
    copies = [(kind, row.title) for kind, row, _ in lines if kind != "total" and row.title.endswith("(copy)")]
    assert copies == [("trip", "Köln – München (copy)"), ("next", "München – Wien (copy)"),
                      ("next", "Wien – Köln (copy)")]


def test_the_copy_journey_button_shows_only_for_a_journey(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    assert f'action="/trips/{trip_id}/copy-journey"' not in c.get(f"/trips/{trip_id}/edit").text
    _journey(sessions, trip_id)
    assert f'action="/trips/{trip_id}/copy-journey"' in c.get(f"/trips/{trip_id}/edit").text


def test_a_request_without_the_csrf_token_is_refused(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _journey(sessions, trip_id)
    assert c.post(f"/trips/{trip_id}/copy-journey", follow_redirects=False).status_code == 403
    assert _copies(sessions) == []
