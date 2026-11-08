"""The tests that check the whole app run in `ship_pr.py` for the files that they check (#730): no import leads from
a new route, a template or a style sheet to them, and 4 of 4 red quick CI runs (2026-11-07) were such tests."""

import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "framework" / "tools"))

import merge_main  # noqa: E402


def _selected(changed):
    tests = {str(Path(f).relative_to(ROOT)): Path(f).read_text(encoding="utf-8")
             for f in glob.glob(str(ROOT / "tests" / "test_*.py"))}
    return set(merge_main.test_files(changed, changed, tests)[0])


def test_a_new_route_runs_the_route_list_test():
    assert "tests/test_trip_delete_pages.py" in _selected(["app/web/export.py"])


def test_a_trip_template_runs_the_form_and_the_checklist_tests():
    got = _selected(["app/web/templates/trip.html"])
    assert {"tests/test_trip_weights_panel.py", "tests/test_page_checklist.py"} <= got


def test_a_style_sheet_runs_the_checklist_test():
    assert "tests/test_page_checklist.py" in _selected(["app/web/static/app.css"])


def test_an_api_route_runs_the_rate_limit_test():
    assert "tests/test_api_routes_limited.py" in _selected(["app/api/trips.py"])
