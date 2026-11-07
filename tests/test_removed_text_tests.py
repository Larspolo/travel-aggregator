"""The tests of a removed page text run before the push (#653): `merge_main.removed_texts` and `text_tests`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "framework" / "tools"))

import merge_main  # noqa: E402

DIFF = "--- a/app/web/templates/trip.html\n+++ b/app/web/templates/trip.html\n@@ -3 +3 @@\n-<span>🚌 Bus</span>\n+<span><svg></svg> Bus</span>\n"


def test_a_removed_emoji_selects_the_test_that_asserts_it():
    texts = merge_main.removed_texts(DIFF, "<span><svg></svg> Bus</span>")
    tests = {"tests/test_bus.py": "assert '🚌' in page", "tests/test_other.py": "assert 'Trips' in page"}
    assert "🚌 Bus" in texts
    assert [f for f, t in tests.items() if merge_main.asserts_removed(t, texts, "<span><svg></svg> Bus</span>")] == ["tests/test_bus.py"]


def test_a_removed_line_whose_text_stays_selects_nothing():
    assert merge_main.removed_texts(DIFF, "<p>🚌 Bus</p>\n<span><svg></svg> Bus</span>") == set()


def test_a_test_that_asserts_only_the_emoji_is_selected():
    new = "<span><svg></svg> Bus</span>"
    texts = merge_main.removed_texts(DIFF, new)
    assert merge_main.asserts_removed("assert '🚌' in page", texts, new)
    assert not merge_main.asserts_removed("assert 'Bus' in page", texts, new)
