"""The stops of a captured SNCF Connect train leg on the trip page: a full path of the epic #2715 (#2717)."""

import re
from pathlib import Path

from tests.test_capture_upload import _post, client, trip_id  # noqa: F401  (fixtures)

FIX = Path(__file__).parent / "fixtures" / "sncf-connect.com" / "search-paris-lyon.json"


def _rows(page):
    """The offer rows of the trip page, each with its detail row: {row id: html}."""
    parts = re.split(r'(?=<tr id="it-)', page)
    return {re.match(r'<tr id="(it-\d+)"', x).group(1): x for x in parts[1:]}


def _row_with(rows, train):
    found = [x for x in rows.values() if re.search(rf"\b{train}\b", x)]
    assert len(found) == 1, f"train {train} in {len(found)} rows"
    return found[0]


def _post_fixture(client, trip_id):  # noqa: F811
    assert _post(client, trip_id, source="sncf-connect.com", content=FIX.read_bytes()).status_code == 303


def test_stops_of_each_train_leg_show_on_the_row(client, trip_id):  # noqa: F811
    _post_fixture(client, trip_id)
    rows = _rows(client.get(f"/trips/{trip_id}").text)
    tgv_6641 = _row_with(rows, "6641")
    assert "1 stop" in tgv_6641 and "Le Creusot - Montceau-Les-Mines - Montchanin TGV" in tgv_6641
    assert "17 stops" in _row_with(rows, "17769")
    assert "leg-stops" not in _row_with(rows, "6603")


def test_via_creusot_shows_only_the_tgv_6641_row(client, trip_id):  # noqa: F811
    _post_fixture(client, trip_id)
    via = client.get(f"/trips/{trip_id}?via=Le%20Creusot").text
    rows = _rows(via)
    assert len(rows) == 1
    assert "6641" in _row_with(rows, "6641")
    hidden = re.search(r"via Le Creusot</a> hides (\d+)", via)
    assert hidden is not None
    assert int(hidden.group(1)) == 2
