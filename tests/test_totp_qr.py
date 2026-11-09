"""The settings page shows the key of the second login step as a QR code (#1317)."""

import os
import pytest
import segno

from app import totp
from tests.test_totp_settings import _card, _start, client  # noqa: F401  (fixture)
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures)


def test_turn_on_shows_one_qr_code_of_the_link(client):  # noqa: F811
    page, secret = _start(client)
    card = _card(page)
    assert card.count("<svg") == 1
    assert segno.make(totp.uri(secret), error="m").svg_inline(scale=4) in card
    assert 'class="totp-key"' in card
    assert 'href="otpauth://totp/' in card


def test_no_qr_code_before_turn_on(client):  # noqa: F811
    assert "<svg" not in _card(client.get("/settings").text).split("</section>")[0]


@pytest.mark.slow
def test_qr_code_fits_390_px(live, days_trip, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base = live.rsplit("/trips/", 1)[0]
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(base + "/settings")
        page.locator('form[action="/settings/totp/start"] button').click()
        page.wait_for_selector(".totp-qr svg")
        box = page.locator(".totp-qr svg").bounding_box()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        page.locator(".totp-qr").scroll_into_view_if_needed()
        page.screenshot(path=str(tmp_path / "qr-390.png"))
        browser.close()
    assert box["width"] > 100 and box["x"] >= 0 and box["x"] + box["width"] <= 390
    assert scroll <= 390
