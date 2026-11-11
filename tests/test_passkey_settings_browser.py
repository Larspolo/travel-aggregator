"""Add a passkey on the settings page with a virtual authenticator, see it in the list and remove it (#1558)."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from app.auth import make_password_hash

pytestmark = pytest.mark.slow
PASSWORD = "pw"


@pytest.fixture
def live(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.delenv("PASSKEY_ORIGIN", raising=False)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    # WebAuthn needs a domain as the relying party id, not an IP address: "localhost" is a secure context
    yield f"http://localhost:{port}"
    server.should_exit = True
    thread.join(5)


def test_add_list_and_remove_a_passkey(live):
    from playwright.sync_api import expect, sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error"
                and not m.location.get("url", "").endswith("/favicon.ico") else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: errors.append("dialog: " + d.message))  # P6: no browser dialog
        cdp = page.context.new_cdp_session(page)
        cdp.send("WebAuthn.enable")
        cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
            "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
            "isUserVerified": True, "automaticPresenceSimulation": True}})
        page.goto(live + "/login")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.goto(live + "/settings")
        expect(page.locator("#passkeys")).to_contain_text("No passkeys yet.")
        page.fill("#passkey-name", "Laptop")
        page.click("#passkey-add button[type=submit]")
        item = page.locator(".passkey-list li")
        expect(item).to_have_count(1)
        expect(item).to_contain_text("Laptop")
        expect(item).to_contain_text("never used")
        expect(item).to_contain_text("added " + time.strftime("%Y-%m-%d", time.gmtime()))
        assert page.evaluate("document.documentElement.scrollWidth") <= 390

        # the same authenticator again: excludeCredentials stops a second credential, nothing new is stored
        page.fill("#passkey-name", "Laptop again")
        page.click("#passkey-add button[type=submit]")
        expect(page.locator("#passkey-status")).to_contain_text("The passkey is not added")
        expect(page.locator(".passkey-list li")).to_have_count(1)

        item.get_by_role("button", name="Remove").click()
        expect(page.locator("#passkeys")).to_contain_text("No passkeys yet.")
        expect(page.locator("main")).to_contain_text("The passkey “Laptop” is removed.")
        assert errors == []
        browser.close()
