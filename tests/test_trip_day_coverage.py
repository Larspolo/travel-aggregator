"""The days view shows the sources with offers on each day and the search links of the other sources (#2058)."""

import re
from datetime import date

from tests.test_trip_days_strip import _on, _set_range, _strip
from tests.test_trip_hide import hide, itinerary_at
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

def _to_berlin(sessions, tid):
    from app.models import Trip
    with sessions() as s:
        s.get(Trip, tid).destination_text = "Berlin"  # a pair with a bahn.de link
        s.commit()


def _cell(html, when):
    strip = _strip(html)
    start = strip.index(f'<span class="day-date">{when}</span>')
    end = strip.find('<span class="day-cell">', start)
    return strip[start:end if end > 0 else len(strip)]

def test_the_sources_and_the_missing_link_of_each_day(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 5, 3), date(2026, 5, 5))
    _to_berlin(sessions, tid)
    ingest(client, auth, tid, [_on("2026-05-03", "89.90", "ICE 1"), _on("2026-05-04", "99.90", "ICE 2")])
    html = client.get(f"/trips/{tid}").text
    for when in ("03-05", "04-05"):
        cell = _cell(html, when)
        assert '<span class="day-searched">bahn.de</span>' in cell
        assert "search bahn.de" not in cell
    cell = _cell(html, "05-05")
    assert "day-searched" not in cell
    link = re.search(r'<a class="day-search" href="([^"]+)" target="_blank" rel="noopener">search bahn.de</a>', cell)
    assert link and "hd=2026-05-05" in link.group(1).replace("&amp;", "&")

def test_a_hidden_itinerary_does_not_count(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 5, 3), date(2026, 5, 4))
    _to_berlin(sessions, tid)
    ingest(client, auth, tid, [_on("2026-05-03", "89.90", "ICE 1"), _on("2026-05-04", "99.90", "ICE 2")])
    assert hide(client, tid, itinerary_at(sessions, tid, "89.90")).status_code == 303
    cell = _cell(client.get(f"/trips/{tid}?show_hidden=true").text, "03-05")
    assert "day-searched" not in cell and "search bahn.de" in cell

def test_a_trip_with_no_date_shows_no_source_line(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, None, None)
    ingest(client, auth, tid, [_on("2026-05-03", "89.90", "ICE 1")])
    assert "day-sources" not in client.get(f"/trips/{tid}").text
