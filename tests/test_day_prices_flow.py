"""The whole feature of epic #1195: the real bahn.de day price captures (#1183) go through /api/ingest and show on
the days of the trip page."""

import json
import re
from datetime import date
from pathlib import Path

from tests.test_bahn_ingest import body
from tests.test_trip_days_strip import _on, _set_range, _strip
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

FIX = Path(__file__).parent / "fixtures" / "bahn.de"
DAYS = ["tagesbestpreis-amsterdam-zuerich-2026-12-01.json", "tagesbestpreis-amsterdam-zuerich-2026-12-02.json"]


def _post_capture(client, auth, tid, name):
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    r = client.post("/api/ingest", json=body(tid, raw), headers=auth)
    assert r.status_code == 200, r.text


def _chip(strip, day):
    """The text of the chip of one day (day-date 'DD-MM') of the strip."""
    m = re.search(r'<span class="day-date">' + day + r'</span>(.*?)(?=<(?:a|span) class="chip day|</nav>)',
                  strip, re.S)
    assert m, f"no chip for {day}"
    return m.group(0)


def test_day_price_captures_show_on_the_days_of_the_trip_page(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 11, 30), date(2026, 12, 4))
    for name in DAYS:
        _post_capture(client, auth, tid, name)
    ingest(client, auth, tid, [_on("2026-12-02", "89.90", "ICE 1")])
    strip = _strip(client.get(f"/trips/{tid}").text)
    assert strip.count('class="day-date"') == 5

    day1 = _chip(strip, "01-12")
    assert "from €49.99 (bahn.de day price)" in day1
    assert "€89.90" not in day1

    day2 = _chip(strip, "02-12")
    assert "€89.90" in day2  # the costs of its connection
    assert "bahn.de day price" not in day2

    for day in ("30-11", "03-12", "04-12"):
        assert "no offers" in _chip(strip, day), day
