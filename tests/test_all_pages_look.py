"""All pages of epic #621 meet the browser points of the page checklist (DESIGN.md section 10); screenshots (#651).

At 390 px each control is 44 px high or more, and a control that has the keyboard focus shows an outline.
The test takes a screenshot of each page at 1280 px and 390 px, in light and dark mode (`SCREENSHOT_DIR`).
"""

import os
import socket
import threading
import time

import pytest
import uvicorn

from app.auth import require_login
from app.main import app
from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

PHONE = 390
DESKTOP = 1280
MIN_HEIGHT = 44

# The visible controls (with "Advanced" and the other <details> open) that are less than 44 px high.
SMALL = """() => {
  document.querySelectorAll('details').forEach(d => d.open = true);
  return [...document.querySelectorAll('input, select, button, textarea, summary, .btn')]
    .filter(e => e.type !== 'hidden' && e.offsetParent !== null)
    .map(e => [e.outerHTML.slice(0, 90), Math.round(e.getBoundingClientRect().height)])
    .filter(([_, h]) => h < %d);
}""" % MIN_HEIGHT

# The focused control has no visible ring: no outline and no box shadow.
NO_RING = """() => {
  const e = document.activeElement;
  if (!e || e === document.body) return null;
  const s = getComputedStyle(e);
  const ring = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none';
  return ring ? null : e.outerHTML.slice(0, 90);
}"""


def _serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    return server, thread, f"http://127.0.0.1:{port}"


def _launch(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()


def _problems(page):
    """Give the controls that are too small on a phone and the focused controls with no ring (first 5 tabs)."""
    found = [f"small {h} px: {html}" for html, h in page.evaluate(SMALL)]
    for _ in range(5):
        page.keyboard.press("Tab")
        bad = page.evaluate(NO_RING)
        if bad:
            found.append(f"no focus ring: {bad}")
    return found


def _check(base, pages, tmp_path):
    from playwright.sync_api import sync_playwright

    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    found = {}
    with sync_playwright() as p:
        browser = _launch(p)
        for scheme in ("light", "dark"):
            for width in (DESKTOP, PHONE):
                ctx = browser.new_context(viewport={"width": width, "height": 844}, color_scheme=scheme,
                                          has_touch=width == PHONE)
                page = ctx.new_page()
                for name, path in pages:
                    response = page.goto(base + path)
                    assert response.status < 400, path
                    page.screenshot(path=os.path.join(shots, f"page-{name}-{width}-{scheme}.png"), full_page=True)
                    if width == PHONE and scheme == "light":
                        bad = _problems(page)
                        if bad:
                            found[path] = bad
                ctx.close()
        browser.close()
    return found


def test_all_pages_look_right(trip, sessions, tmp_path):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer(f"{80 + i}.90", f"ICE {100 + i}") for i in range(3)])
    with sessions() as s:
        a, b = [i.id for i in s.query(Itinerary).filter_by(trip_id=tid).order_by(Itinerary.id).limit(2)]
    pages = [("trips", "/"), ("archive", "/?archived=1"), ("trip", f"/trips/{tid}"), ("trip-new", "/trips/new"),
             ("trip-edit", f"/trips/{tid}/edit"), ("trip-delete", f"/trips/{tid}/delete"),
             ("offer-new", f"/trips/{tid}/offers/new"), ("source-new", "/sources/new"), ("captures", "/captures"),
             ("trip-captures", f"/trips/{tid}/captures"), ("profiles", "/profiles"), ("places", "/places"),
             ("settings", "/settings"), ("rates", "/rates"), ("tokens", "/tokens"),
             ("compare", f"/trips/{tid}/compare?it={a}&it={b}"),
             ("history", f"/trips/{tid}/itineraries/{a}/history"), ("login", "/login")]
    server, thread, base = _serve()
    try:
        found = _check(base, pages, tmp_path)
    finally:
        server.should_exit = True
        thread.join(5)
    assert found == {}, "\n".join(f"{k}: {v}" for k, vs in found.items() for v in vs)


def test_the_empty_pages_look_right(sessions, tmp_path):
    pages = [(f"empty-{n}", p) for n, p in (("trips", "/"), ("captures", "/captures"), ("profiles", "/profiles"),
                                            ("places", "/places"), ("tokens", "/tokens"))]
    app.dependency_overrides[require_login] = lambda: None
    server, thread, base = _serve()
    try:
        found = _check(base, pages, tmp_path)
    finally:
        server.should_exit = True
        thread.join(5)
        app.dependency_overrides.pop(require_login, None)
    assert found == {}, "\n".join(f"{k}: {v}" for k, vs in found.items() for v in vs)


def test_the_checks_find_a_small_control_and_a_missing_ring():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": PHONE, "height": 844})
        page.set_content('<button style="height:30px;outline:none">A</button>')
        bad = _problems(page)
        assert any(b.startswith("small 30 px") for b in bad)
        assert any(b.startswith("no focus ring") for b in bad)
        page.set_content('<style>button:focus-visible{outline:2px solid blue}</style>'
                         '<button style="height:48px">A</button>')
        assert _problems(page) == []
        browser.close()
