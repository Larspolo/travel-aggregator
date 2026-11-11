"""A trip with one date shows the sources and the missing search links of that day (#2068)."""

import re
from datetime import date

from tests.test_trip_day_coverage import _to_berlin
from tests.test_trip_days_strip import _on, _set_range, _strip
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _line(html):
    m = re.search(r'<p id="trip-day-cover".*?</p>', html, re.S)
    assert m, "no line"
    return m.group(0)


def test_one_date_with_an_offer_shows_the_source(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 5, 3), None)
    _to_berlin(sessions, tid)
    ingest(client, auth, tid, [_on("2026-05-03", "89.90", "ICE 1")])
    html = client.get(f"/trips/{tid}").text
    line = _line(html)
    assert '<span class="day-searched">bahn.de</span>' in line and "search bahn.de" not in line
    assert " hidden" in _strip(html).split(">")[0]


def test_one_date_with_no_offer_shows_the_link(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 5, 3), None)
    _to_berlin(sessions, tid)
    line = _line(client.get(f"/trips/{tid}").text)
    link = re.search(r'<a class="day-search" href="([^"]+)"[^>]*>search bahn.de</a>', line)
    assert link and "hd=2026-05-03" in link.group(1).replace("&amp;", "&")
