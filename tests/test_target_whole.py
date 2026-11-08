"""The whole target price of a trip (#866): the marks on the trips list and the trip page, and one message for each
crossing of the target (#845). The parts are in test_target_marks.py (#847) and test_target_notify.py (#848)."""

from tests.test_target_notify import _setup, sent  # noqa: F401  (sent is a fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _marked(client, trip_id):
    """The list shows the text "at target"; the trip page shows its card with id "at-target" (#847)."""
    return "at target" in client.get("/").text, 'id="at-target"' in client.get(f"/trips/{trip_id}").text


def test_a_target_crossing_marks_both_pages_and_sends_one_message(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id, "ntfy", "80.00")
    ingest(client, auth, trip_id, [offer("95.00")])
    assert _marked(client, trip_id) == (False, False)
    assert sent == []

    ingest(client, auth, trip_id, [offer("78.00")])
    assert _marked(client, trip_id) == (True, True)
    assert len(sent) == 1

    ingest(client, auth, trip_id, [offer("78.00")])
    ingest(client, auth, trip_id, [offer("76.00")])
    assert len(sent) == 1
    assert _marked(client, trip_id) == (True, True)


def test_no_target_gives_no_mark_and_no_message(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id, "ntfy", None)
    ingest(client, auth, trip_id, [offer("70.00")])
    assert _marked(client, trip_id) == (False, False)
    assert sent == []
