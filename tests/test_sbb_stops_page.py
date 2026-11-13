"""The stops and platforms of a captured SBB train leg on the trip page: a full path of the epic #2731 (#2734)."""

import re
from pathlib import Path

from tests.test_capture_upload import _post, client, trip_id  # noqa: F401  (fixtures)

FIX = Path(__file__).parent / "fixtures" / "sbb.ch" / "search-basel-zuerich.json"


def _rows(page):
    """The offer rows of the trip page, each with its detail row: {row id: html}."""
    parts = re.split(r'(?=<tr id="it-)', page)
    return {re.match(r'<tr id="(it-\d+)"', x).group(1): x for x in parts[1:]}


def _row_with(rows, train):
    found = [x for x in rows.values() if re.search(rf"\b{train}\b", x)]
    assert len(found) == 1, f"train {train} in {len(found)} rows"
    return found[0]


def _post_fixture(client, trip_id):  # noqa: F811
    assert _post(client, trip_id, source="sbb.ch", content=FIX.read_bytes()).status_code == 303


def test_stops_and_platforms_of_each_sbb_train_show_on_the_row(client, trip_id):  # noqa: F811
    _post_fixture(client, trip_id)
    rows = _rows(client.get(f"/trips/{trip_id}").text)
    ir = _row_with(rows, "1963")
    assert "6 stops" in ir and "Rheinfelden" in ir and "Baden" in ir
    ic = _row_with(rows, "763")
    assert "leg-stops" not in ic
    assert "platform 9" in ic


def test_via_brugg_shows_only_the_ir_1963_row(client, trip_id):  # noqa: F811
    _post_fixture(client, trip_id)
    rows = _rows(client.get(f"/trips/{trip_id}?via=Brugg").text)
    assert len(rows) == 1
    assert "1963" in _row_with(rows, "1963")
