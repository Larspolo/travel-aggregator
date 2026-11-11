"""The trip page warns about another trip in planning on the same route and date (#1592)."""

import re
from datetime import date

from app.models import Trip
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

CARD = r'<section class="duplicates card".*?</section>'


def _set_route(sessions, trip_id, origin, destination, day, end=None):
    with sessions() as s:
        t = s.get(Trip, trip_id)
        t.origin_text, t.destination_text, t.date_from, t.date_to = origin, destination, day, end
        s.commit()


def _add_trip(sessions, origin, destination, day, end=None):
    with sessions() as s:
        other = Trip(title=f"{origin} {destination} {day}", origin_text=origin, destination_text=destination,
                     date_from=day, date_to=end)
        s.add(other)
        s.commit()
        return other.id


def test_a_trip_in_planning_on_the_same_route_and_date_shows_the_warning_with_links(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_route(sessions, trip_id, "Amsterdam", "Zürich", date(2026, 12, 1))
    ingest(client, auth, trip_id, [offer("89.90")])
    other_id = _add_trip(sessions, "Amsterdam", "Zürich", date(2026, 11, 30), date(2026, 12, 2))
    section = re.search(CARD, client.get(f"/trips/{trip_id}").text, re.S)
    assert section is not None
    assert "<h2>A trip on this route and date already exists</h2>" in section.group(0)
    assert f'<a href="/trips/{other_id}">' in section.group(0)
    assert "2026-11-30 to 2026-12-02" in section.group(0)
    assert f'<a href="/trips/{trip_id}/merge">Merge</a>' in section.group(0)


def test_a_trip_with_no_duplicate_has_no_warning(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_route(sessions, trip_id, "Amsterdam", "Zürich", date(2026, 12, 1))
    ingest(client, auth, trip_id, [offer("89.90")])
    _add_trip(sessions, "Amsterdam", "Basel", date(2026, 12, 1))
    _add_trip(sessions, "Amsterdam", "Zürich", date(2026, 12, 8))
    assert 'id="duplicates"' not in client.get(f"/trips/{trip_id}").text
