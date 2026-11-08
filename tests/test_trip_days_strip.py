"""The departure days strip above the table of the trip page (#711)."""

import re
from datetime import date

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _set_range(sessions, tid, start, end):
    from app.models import Trip
    with sessions() as s:
        t = s.get(Trip, tid)
        t.date_from, t.date_to = start, end
        s.commit()


def _on(day, price, service_no):
    o = offer(price, service_no)
    for leg in o["legs"]:
        leg["depart_at"] = leg["depart_at"].replace("2026-12-20", day)
        leg["arrive_at"] = leg["arrive_at"].replace("2026-12-20", day)
    return o


def _strip(html):
    m = re.search(r'<nav id="trip-days".*?</nav>', html, re.S)
    assert m, "no strip"
    return m.group(0)


def test_a_range_of_3_days_shows_3_days_with_costs(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 12, 19), date(2026, 12, 21))
    ingest(client, auth, tid, [_on("2026-12-19", "89.90", "ICE 1"), _on("2026-12-19", "59.90", "ICE 2"),
                               _on("2026-12-20", "119.90", "ICE 3")])
    strip = _strip(client.get(f"/trips/{tid}").text)
    assert " hidden" not in strip.split(">")[0]
    assert strip.count('class="day-date"') == 3
    assert "19-12" in strip and "20-12" in strip and "21-12" in strip
    assert "€59.90" in strip or "59.90" in strip
    assert "no offers" in strip  # the 21st has no offer and is no link
    assert "day=2026-12-21" not in strip
    assert strip.count('class="day-best"') == 2


def test_a_trip_with_1_day_shows_no_strip(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 12, 20), None)
    ingest(client, auth, tid, [offer("89.90")])
    strip = _strip(client.get(f"/trips/{tid}").text)
    assert " hidden>" in strip.split("\n")[0] + ">" or "hidden" in strip.split(">")[0]
    assert "day-date" not in strip


def test_a_day_link_filters_and_marks_the_day(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 12, 19), date(2026, 12, 20))
    ingest(client, auth, tid, [_on("2026-12-19", "89.90", "ICE 1"), _on("2026-12-20", "119.90", "ICE 3")])
    page = client.get(f"/trips/{tid}", params={"day": "2026-12-19"}).text
    strip = _strip(page)
    selected = re.search(r'<a [^>]*aria-current="true"[^>]*>(.*?)</a>', strip, re.S)
    assert selected and "19-12" in selected.group(1)
    assert "ICE 1" in page and "ICE 3" not in page.split('id="table"')[1]
    all_link = re.search(r'<a [^>]*href="([^"]*)"[^>]*>All days</a>', strip).group(1)
    assert "day=" not in all_link
    page = client.get(all_link.replace("&amp;", "&")).text
    assert "ICE 1" in page and "ICE 3" in page
    assert re.search(r'aria-current="true"[^>]*>All days', _strip(page))


def test_a_slider_change_updates_the_strip_and_keeps_the_day(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 12, 19), date(2026, 12, 20))
    ingest(client, auth, tid, [_on("2026-12-19", "89.90", "ICE 1"), _on("2026-12-20", "119.90", "ICE 3")])
    before = _strip(client.get(f"/trips/{tid}", params={"day": "2026-12-19"}).text)
    r = client.get(f"/trips/{tid}", params={"day": "2026-12-19", "hour_markup": "90"},
                   headers={"HX-Request": "true"})
    strip = _strip(r.text)
    assert 'hx-swap-oob="true"' in strip
    assert re.search(r'aria-current="true"[^>]*>\s*<span class="day-date">19-12', strip)
    assert re.findall(r'day-best[^>]*>([^<]*)', strip) != re.findall(r'day-best[^>]*>([^<]*)', before)
    assert "day=2026-12-19" in strip  # the links keep the new weights
    assert "hour_markup=90" in strip
