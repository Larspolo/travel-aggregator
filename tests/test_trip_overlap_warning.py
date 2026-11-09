"""The trip page warns about booked journeys that conflict with another booked journey (#1655)."""

import re
from datetime import datetime, timedelta, timezone

from app.models import Itinerary, Trip
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

CARD = r'<section class="booked-conflicts card".*?</section>'
ZURICH = timezone(timedelta(minutes=60))


def _journey(s, trip_id, depart, arrive, fingerprint):
    s.add(Itinerary(trip_id=trip_id, fingerprint=fingerprint, depart_at=depart, arrive_at=arrive,
                    duration_min=int((arrive - depart).total_seconds() // 60), booked=True))


def _next_trip(sessions, outbound_id):
    with sessions() as s:
        nxt = Trip(title="Return", status="planning", return_of_id=outbound_id)
        s.add(nxt)
        s.commit()
        return nxt.id


def test_next_trip_departing_before_the_outbound_arrives_shows_the_order_warning(trip, sessions):  # noqa: F811
    client, auth, outbound_id = trip
    next_id = _next_trip(sessions, outbound_id)
    with sessions() as s:
        _journey(s, outbound_id, datetime(2031, 12, 1, 10, tzinfo=ZURICH), datetime(2031, 12, 1, 16, 2, tzinfo=ZURICH), "out")
        _journey(s, next_id, datetime(2031, 12, 1, 14, tzinfo=ZURICH), datetime(2031, 12, 1, 18, tzinfo=ZURICH), "back")
        s.commit()
    section = re.search(CARD, client.get(f"/trips/{next_id}").text, re.S)
    assert section is not None
    assert "This journey departs before the journey before it arrives" in section.group(0)
    assert f'<a href="/trips/{outbound_id}">' in section.group(0)
    assert 'class="booked-conflicts' not in client.get(f"/trips/{outbound_id}").text


def test_an_unbooked_overlap_shows_no_warning(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    with sessions() as s:
        other = Trip(title="Other", status="planning")
        s.add(other)
        s.commit()
        _journey(s, trip_id, datetime(2031, 12, 2, 10, tzinfo=ZURICH), datetime(2031, 12, 2, 12, tzinfo=ZURICH), "a")
        s.add(Itinerary(trip_id=other.id, fingerprint="b", depart_at=datetime(2031, 12, 2, 11, tzinfo=ZURICH),
                        arrive_at=datetime(2031, 12, 2, 13, tzinfo=ZURICH), duration_min=120, booked=False))
        s.commit()
    assert 'id="booked-conflicts"' not in client.get(f"/trips/{trip_id}").text


def test_overlapping_journeys_of_two_trips_show_the_overlap_warning(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    with sessions() as s:
        other = Trip(title="Other", status="planning")
        s.add(other)
        s.commit()
        _journey(s, trip_id, datetime(2031, 12, 2, 10, tzinfo=ZURICH), datetime(2031, 12, 2, 12, tzinfo=ZURICH), "a")
        _journey(s, other.id, datetime(2031, 12, 2, 11, tzinfo=ZURICH), datetime(2031, 12, 2, 13, tzinfo=ZURICH), "b")
        s.commit()
        other_id = other.id
    section = re.search(CARD, client.get(f"/trips/{trip_id}").text, re.S)
    assert section is not None
    assert "This journey overlaps another booked journey" in section.group(0)
    assert f'<a href="/trips/{other_id}">' in section.group(0)
