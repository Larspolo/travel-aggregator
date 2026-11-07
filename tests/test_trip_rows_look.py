"""The ranked rows and the phone cards of the trip page are short and use one money format (#627)."""

import os
import re
from decimal import Decimal

import pytest

from app.web.pages import money
from tests.test_mobile_whole import DESKTOP, PHONE, _launch, live  # noqa: F401  (live is a fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

# The text lines of the highest row: the height of the row in units of the body line height.
ROW_LINES = """() => {
  const lh = parseFloat(getComputedStyle(document.body).lineHeight);
  return [...document.querySelectorAll('#table tbody tr:not(.detail)')].map(tr => {
    const cs = getComputedStyle(tr.cells[0]);
    return (tr.getBoundingClientRect().height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom) - 1) / lh;
  });
}"""


def test_the_money_filter_puts_the_symbol_first_and_keeps_the_code_with_no_symbol():
    assert money(Decimal("80.9")) == "€80.90"
    assert money(Decimal("208.9"), "EUR") == "€208.90"
    assert money(Decimal("23.49"), "GBP") == "£23.49"
    assert money(Decimal("120"), "CHF") == "CHF 120.00"


def test_a_eur_row_has_one_money_format_and_the_check_box_is_in_the_actions(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("80.90", "ICE 105"), offer("119.90", "ICE 123")])
    page = client.get(f"/trips/{trip_id}").text
    rows = page[page.index('<tbody id="rows">'):page.index("</tbody>")]
    assert "EUR " not in rows
    assert '<td class="price">€80.90</td>' in rows and '<td class="price">€119.90</td>' in rows
    assert len(re.findall(r'<div class="total">€\d+\.\d\d</div>', rows)) == 2
    for row in rows.split('<tr class="detail">')[:-1]:
        actions = row[row.index('<td class="actions">'):]
        assert 'name="it"' in actions and 'name="it"' not in row[:row.index('<td class="actions">')]
    # "stale" is a short badge; the long text is in its title
    assert "stale, price may have changed</span>" not in page


@pytest.mark.slow
def test_a_row_is_at_most_4_lines_and_a_card_ends_with_the_check_box(live, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, tid = live
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))  # CI uploads them as the artifact "screenshots"
    os.makedirs(shots, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        for scheme in ("light", "dark"):
            desk = browser.new_page(viewport={"width": DESKTOP, "height": 800}, color_scheme=scheme,
                                    device_scale_factor=2)
            desk.goto(f"{base}/trips/{tid}")
            lines = desk.evaluate(ROW_LINES)
            assert len(lines) == 20 and max(lines) <= 4, lines
            assert desk.evaluate("document.documentElement.scrollWidth") <= DESKTOP
            desk.screenshot(path=f"{shots}/trip-1280-{scheme}.png")
            desk.close()

            phone = browser.new_page(viewport={"width": PHONE, "height": 800}, color_scheme=scheme,
                                     device_scale_factor=2)
            phone.goto(f"{base}/trips/{tid}")
            assert phone.evaluate("document.documentElement.scrollWidth") <= PHONE
            card = phone.locator("#table tbody tr:not(.detail)").first
            box = card.locator('input[name="it"]').bounding_box()
            for cell in ("td.route", "td.cost", "td.carrier", "td.price"):
                top = card.locator(cell).first.bounding_box()
                assert box["y"] >= top["y"] + top["height"] - 1, cell  # the check box is under each value
            assert box["width"] >= 40 and box["height"] >= 40
            phone.screenshot(path=f"{shots}/trip-390-{scheme}.png")
            phone.close()
        browser.close()
