"""The marks of the shared link on the owner's trip page (#1783, epic #1780)."""

import re

from fastapi.testclient import TestClient

from app.main import app
from app.models import ShareMark
from tests.test_share import _setup, share
from tests.test_share_marks import _rows
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def _order(page):
    return re.findall(r'<tr id="it-(\d+)"', page)


def test_a_mark_shows_a_chip_and_the_escaped_note_and_keeps_the_order(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    before = client.get(f"/trips/{trip_id}").text
    assert "Suits partner" not in before and "marked on the shared link" not in before
    TestClient(app).post(f"{link}/marks/{rows['ICE 123']}")
    with sessions() as s:
        s.query(ShareMark).one().note = "<b>ok</b> for me"
        s.commit()
    page = client.get(f"/trips/{trip_id}").text
    assert _order(page) == _order(before)
    row = page.split(f'<tr id="it-{rows["ICE 123"]}"')[1].split('<tr id="it-')[0]
    assert "Suits partner</span>" in row
    assert "Partner: &lt;b&gt;ok&lt;/b&gt; for me" in row and "<b>ok</b>" not in page
    assert page.count("Suits partner</span>") == 1
    assert "1 itinerary marked on the shared link" in page
