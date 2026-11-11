"""A run of some slow test files is its own check kind, apart from the full slow suite (#822)."""

import tokens


def test_slow_files_are_their_own_kind():
    assert tokens.check("python3 -m pytest -m slow tests/test_a_browser.py") == "pytest -m slow files"
    assert tokens.check("python3 -m pytest tests/test_a_browser.py -m slow -x") == "pytest -m slow files"


def test_the_full_slow_suite_keeps_its_kind():
    assert tokens.check("python3 -m pytest -m slow") == "pytest -m slow"
    assert tokens.check("python3 -m pytest -m slow -n auto 2>&1 | tail -5") == "pytest -m slow"


def test_files_with_no_slow_mark_stay_pytest_files():
    assert tokens.check("python3 -m pytest tests/test_a.py") == "pytest files"
