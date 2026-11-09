"""The trip page shows the best offer that the filters hide (#1454)."""

import html
import re
from datetime import datetime, timedelta, timezone

import app.departed
import app.gone
from app.gone import GoneMark
from app.models import Itinerary
from tests.test_trip_hide import itinerary_at

from tests.test_filtered_counts import TWO
from tests.test_trip_filters_whole import PASS, itinerary
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _line(page):
    m = re.search(r'<p id="trip-best-hidden"[^>]*>(.*?)</p>', page, re.S)
    return html.unescape(m.group(1)) if m else ""


def test_the_cheaper_offer_with_a_transfer_is_the_best_hidden_offer(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "100.00", PASS), itinerary("TWO 1", "80.00", TWO)])
    line = _line(client.get(f"/trips/{trip_id}?max_transfers=0&hour_markup=0&transfer_markup=0").text)
    assert "Best hidden offer: €80.00" in line
    assert "hidden by max transfers 0" in line
    assert "€20.00 less than the best shown offer" in line
    link = html.unescape(re.search(r'href="([^"]+)">Show it', line).group(1))
    assert "max_transfers" not in link
    page = client.get(link.split("#")[0]).text
    assert f'id="{link.split("#")[1]}"' in page
    assert not _line(client.get(f"/trips/{trip_id}").text)  # no filter: no line


def test_a_hide_departed_or_gone_row_is_never_the_best_hidden_offer(trip, sessions, monkeypatch):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "100.00", PASS), itinerary("TWO 1", "80.00", TWO)])
    two = itinerary_at(sessions, trip_id, "80.00")
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(app.departed, "clock", lambda: now)
    url = f"/trips/{trip_id}?max_transfers=0&show_hidden=true&show_departed=true"
    assert "Best hidden offer" in _line(client.get(url).text)
    with sessions() as s:
        s.get(Itinerary, two).hidden = True
        s.commit()
    assert not _line(client.get(url).text)  # the action "Hide"
    with sessions() as s:
        it = s.get(Itinerary, two)
        it.hidden, it.depart_at = False, datetime.now(timezone.utc) - timedelta(hours=1)
        s.commit()
    assert not _line(client.get(url).text)  # departed
    with sessions() as s:
        it = s.get(Itinerary, two)
        it.depart_at = datetime.now(timezone.utc) + timedelta(days=30)
        fare_ids = [f.id for f in it.fares]
        s.commit()
    assert "Best hidden offer" in _line(client.get(url).text)
    marks = {i: GoneMark("bahn.de", datetime.now(timezone.utc)) for i in fare_ids}
    monkeypatch.setattr(app.gone, "gone_fares", lambda session, trip_ids: marks)
    assert not _line(client.get(url).text)  # only gone fares
