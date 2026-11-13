"""The via filter on a captured bahn.de payload: a full path of the epic #2699 (#2702)."""

import re

from tests.test_capture_upload import FIX, _post, client, trip_id  # noqa: F401  (fixtures)


def _line(page):
    m = re.search(r"Filters hide (\d+) of (\d+) offers", page)
    return (int(m.group(1)), int(m.group(2))) if m else (0, None)


def test_via_hannover_hides_the_rows_without_that_place(client, trip_id):  # noqa: F811
    assert _post(client, trip_id, content=FIX.read_bytes()).status_code == 303
    everything = client.get(f"/trips/{trip_id}").text
    via = client.get(f"/trips/{trip_id}?via=Hannover").text
    hidden, total = _line(via)
    assert total is not None and 0 < hidden < total
    assert "via Hannover" in via
    assert "Hannover" in everything


def test_a_longer_via_text_shows_the_same_rows(client, trip_id):  # noqa: F811
    assert _post(client, trip_id, content=FIX.read_bytes()).status_code == 303
    short = _line(client.get(f"/trips/{trip_id}?via=Hannover").text)
    longer = _line(client.get(f"/trips/{trip_id}?via=hannover%20hbf").text)
    assert short[0] > 0 and longer == short
