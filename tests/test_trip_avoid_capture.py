"""The avoid filter on a captured bahn.de payload: a full path of the epic #2719 (#2721)."""

import re

from tests.test_capture_upload import FIX, _post, client, trip_id  # noqa: F401  (fixtures)


def _line(page):
    m = re.search(r"Filters hide (\d+) of (\d+) offers", page)
    return (int(m.group(1)), int(m.group(2))) if m else (0, None)


def test_avoid_hannover_hides_the_rows_that_pass_that_place(client, trip_id):  # noqa: F811
    assert _post(client, trip_id, content=FIX.read_bytes()).status_code == 303
    everything = client.get(f"/trips/{trip_id}").text
    via = client.get(f"/trips/{trip_id}?via=Hannover").text
    avoid = client.get(f"/trips/{trip_id}?avoid=Hannover").text
    hidden, total = _line(avoid)
    assert (hidden, total) == (2, 4)  # the fixture has 4 connections, 2 of them pass Hannover Hbf
    assert "Filters hide 2 of 4 offers" in avoid and "avoid Hannover</a> hides 2" in avoid
    # the rows that the via filter hides are the rows that the avoid filter shows, and the reverse
    assert _line(via) == (2, 4)
    assert "Hannover" in everything
