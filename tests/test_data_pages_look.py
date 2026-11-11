"""The data pages show their tables in cards with status chips and an empty state (#632)."""

import re

from tests.test_captures_result_page import _add_capture, _batch
from tests.test_reparse import setup as reparse_setup  # noqa: F401  (fixture: logged-in client)


def test_the_capture_result_is_a_chip_with_a_text_in_a_card(reparse_setup, sessions):  # noqa: F811
    c, auth, trip_id = reparse_setup
    _batch(c, auth, trip_id)
    _add_capture(sessions, trip_id, offer_count=2, rejected_count=0, errors_json=[])
    for page in (f"/trips/{trip_id}/captures", "/captures"):
        text = c.get(page).text
        assert '<section class="card data-card">' in text and "<thead>" in text, page
        assert '<span class="chip good">ok</span>' in text, page
        assert '<span class="chip danger">failed</span>' in text, page
        assert re.search(r'class="toolbar">\s*<a class="btn" href="[^"]*\?failed=1">Only failed captures', text), page


def test_with_no_captures_the_page_shows_the_empty_state_with_a_link_to_the_userscripts(reparse_setup):  # noqa: F811
    c, _auth, trip_id = reparse_setup
    text = c.get(f"/trips/{trip_id}/captures").text
    empty = text[text.index('<div class="empty">'):]
    assert "No captures yet" in empty and 'href="/tokens"' in empty
    assert "<table" not in text
