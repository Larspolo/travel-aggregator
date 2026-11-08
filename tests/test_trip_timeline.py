"""The timeline of the itineraries on the trip page (#815)."""

import re
from datetime import date

from app.models import Itinerary
from tests.test_trip_days_strip import _on, _set_range
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _timeline(html):
    m = re.search(r'<details id="trip-timeline".*?</details>', html, re.S)
    assert m, "no timeline"
    return m.group(0)


def _three(client, auth, tid, sessions):
    _set_range(sessions, tid, date(2026, 12, 19), date(2026, 12, 20))
    ingest(client, auth, tid, [_on("2026-12-19", "89.90", "ICE 1"), _on("2026-12-19", "99.90", "ICE 2"),
                               _on("2026-12-20", "119.90", "ICE 3")])
    with sessions() as s:
        return {it.id for it in s.query(Itinerary).filter_by(trip_id=tid)}


def test_three_itineraries_on_two_days_give_two_blocks_and_three_bar_links(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    ids = _three(client, auth, tid, sessions)
    tl = _timeline(client.get(f"/trips/{tid}").text)
    assert tl.count('class="timeline-day"') == 2
    links = {int(i) for i in re.findall(r'class="timeline-bar[^"]*" href="#it-(\d+)"', tl)}
    assert links == ids and len(re.findall(r'href="#it-', tl)) == 3
    assert 'aria-label="Amsterdam Centraal → Zürich HB, 07:34 to 15:26, 1 transfer, €89.90"' in tl
    assert tl.count("best-value") >= 1 and "<summary>Timeline</summary>" in tl


def test_a_slider_change_gives_a_new_timeline_and_the_day_filter_shows_one_day(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _three(client, auth, tid, sessions)
    r = client.get(f"/trips/{tid}", params={"hour_markup": "90", "max_transfers": "0"},
                   headers={"HX-Request": "true"})
    tl = _timeline(r.text)
    assert 'hx-swap-oob="true"' in tl and 'href="#it-' not in tl  # no row has 0 transfers
    tl = _timeline(client.get(f"/trips/{tid}", params={"day": "2026-12-20"}, headers={"HX-Request": "true"}).text)
    assert tl.count('class="timeline-day"') == 1 and len(re.findall(r'href="#it-', tl)) == 1
