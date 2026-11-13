"""The high notice markup with a captured bahn.de payload (#2697, epic #2694): the Köln → München fixture gives
the ICE 519 connection one notice part, and a connection with no high notice gets no notice part."""

import re

from tests.test_load_markup_capture import _auth, _post, koeln_muenchen
from tests.test_trip_booked import trip  # noqa: F401 (fixture)


def _rows(page):
    """Each offer: its id ("it-N") and its block, the main row and its detail rows (up to the next offer)."""
    blocks = re.split(r'(?=<tr id="it-\d+">)', page)[1:]
    return {int(re.match(r'<tr id="it-(\d+)">', b).group(1)): b.split("</table>")[0] for b in blocks}


def _breakdown(block):
    return re.search(r'<div class="breakdown">(.*?)</div>', block, re.S).group(1)


def _ice_519_row(rows):
    return next(block for block in rows.values() if "Deutsche Bahn ICE 519" in block)


def _no_notice_row(rows):
    return next(block for block in rows.values() if "IC 2048" in block and 'badge notice' not in block)


def test_the_ice_519_connection_gets_one_notice_part_of_15(trip, sessions):  # noqa: F811
    client, trip_id = trip
    _post(client, _auth(sessions), trip_id, koeln_muenchen())
    rows = _rows(client.get(f"/trips/{trip_id}", params={"notice_markup": "15"}).text)
    parts = re.findall(r"€15 notice: [^=<]+", _breakdown(_ice_519_row(rows)))
    assert [p.strip() for p in parts] == ["€15 notice: All seats are already fully …"]
    # both high notices of the connection are shown in its detail
    detail = _ice_519_row(rows)
    assert "All seats are already fully booked (1st class)" in detail
    assert "Track repairs" in detail


def test_a_connection_with_no_high_notice_gets_no_notice_part(trip, sessions):  # noqa: F811
    client, trip_id = trip
    _post(client, _auth(sessions), trip_id, koeln_muenchen())
    rows = _rows(client.get(f"/trips/{trip_id}", params={"notice_markup": "15"}).text)
    assert "notice:" not in _breakdown(_no_notice_row(rows))


def test_without_notice_markup_no_row_shows_a_notice_part_and_costs_stay(trip, sessions):  # noqa: F811
    client, trip_id = trip
    _post(client, _auth(sessions), trip_id, koeln_muenchen())
    plain = _rows(client.get(f"/trips/{trip_id}").text)
    zero = _rows(client.get(f"/trips/{trip_id}", params={"notice_markup": "0"}).text)
    assert all("notice:" not in _breakdown(block) for block in plain.values())
    assert _breakdown(_no_notice_row(plain)) == _breakdown(_no_notice_row(zero))
    assert _breakdown(_ice_519_row(plain)) == _breakdown(_ice_519_row(zero))
