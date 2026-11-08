"""The timeline shows a bar only for the rows that the table shows: a hidden row has no bar, and
"show hidden" adds its bar (#838, criterion 1 of epic #812)."""

import re
from datetime import date

from tests.test_trip_days_strip import _on, _set_range
from tests.test_trip_hide import hide, itinerary_at
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_timeline import _timeline  # noqa: F401  (helper)


def _three_with_one_hidden(client, auth, tid, sessions):
    _set_range(sessions, tid, date(2026, 12, 19), date(2026, 12, 20))
    ingest(client, auth, tid, [_on("2026-12-19", "89.90", "ICE 1"), _on("2026-12-19", "99.90", "ICE 2"),
                               _on("2026-12-20", "119.90", "ICE 3")])
    hidden = itinerary_at(sessions, tid, "89.90")
    assert hide(client, tid, hidden).status_code == 303
    return hidden


def test_a_hidden_row_has_no_bar_and_show_hidden_adds_it(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    hidden = _three_with_one_hidden(client, auth, tid, sessions)

    tl = _timeline(client.get(f"/trips/{tid}").text)
    assert len(re.findall(r'class="timeline-bar[^"]*" href="#it-\d+"', tl)) == 2
    assert f'href="#it-{hidden}"' not in tl

    tl = _timeline(client.get(f"/trips/{tid}?show_hidden=true").text)
    assert len(re.findall(r'class="timeline-bar[^"]*" href="#it-\d+"', tl)) == 3
    assert f'href="#it-{hidden}"' in tl
