"""The open app bar menu on a phone is on top of the page, and a tap on each of its links opens the page (#688).

The bar clipped all below its own bottom edge (`clip-path` of `nav.topbar`), so the open menu showed the page
content in its place and a tap went to the page under it.
"""

import os
import re
import socket
import threading
import time

import pytest

from app.auth import make_password_hash
from app.models import Trip

PASSWORD = "pw"

# The element at the centre of each menu link must be the link or a part of it.
ON_TOP = """() => [...document.querySelectorAll('.menu-links a')].map(a => {
  const r = a.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return a.contains(hit);
})"""


@pytest.mark.slow
def test_open_phone_menu_is_on_top_and_its_links_work(sessions, monkeypatch):
    import uvicorn
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        trip = Trip(title="Amsterdam to Berlin", origin_text="Amsterdam", destination_text="Berlin")
        s.add(trip)
        s.commit()
        tid = trip.id
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
            page = ctx.new_page()
            page.goto(base + "/login")
            page.fill('input[name="password"]', PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_url(re.compile(r".*/$"))
            for path in ("/", f"/trips/{tid}", "/settings"):
                page.goto(base + path)
                page.locator("details.menu summary").tap()
                page.wait_for_function("document.querySelector('details.menu').open")
                assert all(page.evaluate(ON_TOP)), path
            page.goto(base + "/")
            page.locator("details.menu summary").tap()
            page.wait_for_function("document.querySelector('details.menu').open")
            page.locator(".menu-links a", has_text="Settings").tap()
            page.wait_for_url(re.compile(r".*/settings$"))
            ctx.close()
            browser.close()
    finally:
        server.should_exit = True
