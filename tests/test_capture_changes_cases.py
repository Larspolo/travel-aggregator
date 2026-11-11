"""The changes of a capture after a repeat, a move to another trip and a delete (epic #2327, #2328).

The move and the delete use the stub parser of `tests/test_capture_move.py`: its raw is a list of offers."""

from datetime import UTC

from sqlalchemy import select

from app import ingest
from app.capture_changes import capture_changes
from app.capture_delete import delete_capture
from app.models import Capture, Itinerary
from tests.test_capture_move import _capture, _offer, _trip, stub  # noqa: F401  (stub is a fixture)
from tests.test_trip_page import ingest as post_ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _ids(s, trip_id):
    """{departure hour: itinerary id} of the trip."""
    out = {}
    for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)):
        out[it.depart_at.astimezone(UTC).hour + 1] = it.id
    return out


def test_a_repeat_of_the_same_offers_and_prices_is_no_change(sessions, stub):  # noqa: F811
    with sessions() as s:
        a = _trip(s, "A")
        _capture(s, a, [_offer(8, "10.50"), _offer(9, "20.00")], day=1)
        second = _capture(s, a, [_offer(8, "10.50"), _offer(9, "20.00")], day=2)
        changes = capture_changes(s, [second.id])[second.id]
        assert not (changes.new or changes.lower or changes.higher)


def test_a_repeat_with_the_same_prices_shows_no_change_on_the_page(sessions, trip):  # noqa: F811
    client, auth, trip_id = trip
    post_ingest(client, auth, trip_id, [offer("89.90")])
    post_ingest(client, auth, trip_id, [offer("89.90")])
    page = client.get(f"/trips/{trip_id}/captures").text
    assert "no change" in page


def test_a_moved_capture_counts_only_its_present_rows_in_the_new_trip(sessions, stub):  # noqa: F811
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        _capture(s, a, [_offer(8, "10.00"), _offer(9, "20.00")], day=1)
        second = _capture(s, a, [_offer(8, "8.00"), _offer(9, "25.00")], day=2)
        before = capture_changes(s, [second.id])[second.id]
        a_ids = set(_ids(s, a).values())
        assert before.lower == {_ids(s, a)[8]} and before.higher == {_ids(s, a)[9]}
        ingest.move_capture(s, second, b)
        s.commit()
    with sessions() as s:
        moved = s.get(Capture, second.id)
        changes = capture_changes(s, [moved.id])[moved.id]
        b_ids = set(_ids(s, b).values())
        assert changes.new == b_ids  # each journey of the new trip has only this capture's row
        assert changes.lower == set() and changes.higher == set()
        assert not (a_ids & (changes.new | changes.lower | changes.higher))
        first = s.scalars(select(Capture).where(Capture.trip_id == a).order_by(Capture.id)).first()
        old = capture_changes(s, [first.id])[first.id]
        assert old.lower == set() and old.higher == set()


def test_a_deleted_capture_leaves_the_counts_of_the_others_on_present_rows(sessions, stub):  # noqa: F811
    with sessions() as s:
        a = _trip(s, "A")
        _capture(s, a, [_offer(8, "10.00"), _offer(9, "20.00")], day=1)
        second = _capture(s, a, [_offer(8, "8.00"), _offer(9, "20.00")], day=2)
        third = _capture(s, a, [_offer(9, "30.00")], day=3)
        assert capture_changes(s, [third.id])[third.id].higher == {_ids(s, a)[9]}
        delete_capture(s, third)
        s.commit()
        remaining = capture_changes(s, [second.id, third.id])
        assert remaining[second.id].lower == {_ids(s, a)[8]}
        assert remaining[second.id].higher == set()
        assert remaining[third.id].new == set() and remaining[third.id].lower == set()
        assert remaining[third.id].higher == set()
