"""The panel shows the travelers warning of the server (#765) as it is: "These offers are for 1 traveler; the trip has
2" (owner check of #945, 2026-11-08). A places or date warning keeps the short text of #557. Playwright stubs
GM_xmlhttpRequest, so no request goes to a server or a travel site (P1)."""

import json

import pytest

from tests.test_panel_mismatch import WARNING, page, panel, send_with_body  # noqa: F401 (page is a fixture)

pytestmark = pytest.mark.slow
TRAVELERS = "These offers are for 1 traveler; the trip has 2"


def test_a_travelers_warning_shows_the_text_of_the_server(page):  # noqa: F811
    send_with_body(page, json.dumps({"accepted": 1, "warning": TRAVELERS, "mismatch": "travelers"}))
    assert panel(page) == {"text": "Captured 1 offers → sent ✓, but these offers are for 1 traveler; the trip has 2",
                           "kind": "warn"}


def test_a_travelers_warning_keeps_the_best_after_it(page):  # noqa: F811
    send_with_body(page, json.dumps({"accepted": 1, "warning": TRAVELERS, "mismatch": "travelers",
                                     "best": {"total": "165.50", "new": False}}))
    text = panel(page)["text"]
    assert text.startswith("Captured 1 offers → sent ✓, but these offers are for 1 traveler; the trip has 2")
    assert text.endswith("€165.50")


def test_a_places_warning_keeps_the_short_text(page):  # noqa: F811
    send_with_body(page, json.dumps({"accepted": 1, "warning": "These offers do not match the trip (places)",
                                     "mismatch": "places"}))
    assert panel(page) == {"text": WARNING, "kind": "warn"}
