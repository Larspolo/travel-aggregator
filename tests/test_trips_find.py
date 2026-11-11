"""`find_journeys()` gives the trips list lines that contain a search text (#1220)."""

from datetime import date

from app.trips import TripRow, archived_journeys, find_journeys


def _row(id, title, origin="Amsterdam", destination="Berlin", notes=None, return_of_id=None, status="planning"):
    return TripRow(id=id, title=title, origin_text=origin, destination_text=destination, date_from=date(2026, 12, id),
                   date_to=None, status=status, offer_count=0, best_price=None, best_currency=None,
                   return_of_id=return_of_id, notes=notes)


ROWS = [
    _row(1, "Work trip", destination="Zürich"),
    _row(2, "Zürich Christmas", origin="Utrecht", destination="Basel"),
    _row(3, "Paris weekend", destination="Paris"),
    _row(4, "Visit", destination="Rome", notes="with Anna"),
    _row(5, "Out", destination="Madrid"),
    _row(6, "Back", origin="Lisbon", destination="Amsterdam", return_of_id=5),
]


def _titles(text):
    return [t.title for kind, t, _ in find_journeys(ROWS, text, False) if kind != "total"]


def test_a_place_or_a_title_matches_with_no_case_and_no_diacritics():
    assert _titles("zur") == ["Work trip", "Zürich Christmas"]
    assert _titles("ZUR") == _titles("zür") == _titles("zur")


def test_the_note_matches():
    assert _titles("anna") == ["Visit"]


def test_a_match_of_the_return_trip_gives_the_whole_journey():
    lines = find_journeys(ROWS, "lisbon", False)
    assert [(kind, t.title) for kind, t, _ in lines] == [("trip", "Out"), ("return", "Back"), ("total", "Back")]


def test_a_blank_text_gives_all_lines():
    assert find_journeys(ROWS, "  ", False) == archived_journeys(ROWS, False)
    assert find_journeys(ROWS, "", True) == archived_journeys(ROWS, True)
