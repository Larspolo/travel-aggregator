"""Log in with a passkey of a virtual authenticator, and see the message of a removed passkey (#1559)."""

import os
import time

import pytest

from tests.test_passkey_settings_browser import PASSWORD, live  # noqa: F401  (live is a fixture)

pytestmark = pytest.mark.slow
AUTHENTICATOR = {"protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
                 "isUserVerified": True, "automaticPresenceSimulation": True}


def _password_login(page, live):  # noqa: F811
    page.goto(live + "/login")
    page.fill("input[name=password]", PASSWORD)
    page.click("form.login-form button[type=submit]")
    page.wait_for_url(live + "/")


def _add_passkey(page, live, name):  # noqa: F811
    from playwright.sync_api import expect

    page.goto(live + "/settings")
    page.fill("#passkey-name", name)
    page.click("#passkey-add button[type=submit]")
    expect(page.locator(".passkey-list")).to_contain_text(name)


def test_log_in_with_a_passkey_and_see_a_removed_one(live):  # noqa: F811
    from playwright.sync_api import expect, sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error"
                and not m.location.get("url", "").endswith("/favicon.ico")
                and "401" not in m.text else None)  # the 401 of the removed passkey below
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: errors.append("dialog: " + d.message))  # P6: no browser dialog
        cdp = page.context.new_cdp_session(page)
        cdp.send("WebAuthn.enable")
        laptop = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": AUTHENTICATOR})["authenticatorId"]

        _password_login(page, live)
        _add_passkey(page, live, "Laptop")
        page.goto(live + "/logout")
        page.click("#passkey-login-button")
        page.wait_for_url(live + "/")  # no password, no code
        page.goto(live + "/settings")
        today = time.strftime("%Y-%m-%d", time.gmtime())
        expect(page.locator(".passkey-list li")).to_contain_text("last use " + today)
        expect(page.locator(".login-log")).to_contain_text("login with passkey")

        # a second device: its passkey is removed on the settings page, then it tries to log in
        cdp.send("WebAuthn.removeVirtualAuthenticator", {"authenticatorId": laptop})
        cdp.send("WebAuthn.addVirtualAuthenticator", {"options": AUTHENTICATOR})
        _add_passkey(page, live, "Phone")
        page.locator(".passkey-list li", has_text="Phone").get_by_role("button", name="Remove").click()
        expect(page.locator(".passkey-list li")).to_have_count(1)
        page.goto(live + "/logout")
        page.click("#passkey-login-button")
        expect(page.locator("#passkey-login-status")).to_contain_text("not known here")
        assert page.url == live + "/login"
        assert page.evaluate("document.documentElement.scrollWidth") <= 390

        _password_login(page, live)
        page.goto(live + "/settings")
        expect(page.locator(".login-log")).to_contain_text("failed (passkey)")
        assert errors == []
        browser.close()
