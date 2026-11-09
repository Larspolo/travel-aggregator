"""The source status and its warning as a whole, in a browser (#727, part of #723): from the failed captures to the
warning on the trips list and its link to the failed captures of the source."""

import copy
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_all_pages_look import _launch, _serve
from tests.test_ingest_api import BODY
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

BAHN = BODY["source"]
NS = "nsinternational.com"
T0 = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
WARNING = "bahn.de: the last 3 captures failed"


def _post(client, auth, trip_id, source, hour, version, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, parser_version=version,
                captured_at=(T0 + timedelta(hours=hour)).isoformat(), offers=offers)
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200
    return r.json()


def _bad_offer():
    """An offer without a price: the schema rejects it, so the capture counts as failed (#54, #349)."""
    o = offer("89.90")
    del o["price_amount"]
    return o


def test_failed_captures_warn_on_the_trips_list_and_link_to_them(trip, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, tid = trip
    _post(client, auth, tid, BAHN, 0, "1.0.0", [offer("89.90")])
    _post(client, auth, tid, NS, 1, "1.0.0", [offer("95.00")])
    for hour in (2, 3, 4):
        assert _post(client, auth, tid, BAHN, hour, "1.1.0", [_bad_offer()])["rejected"] == 1

    server, thread, base = _serve()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": 1280, "height": 844})

            page.goto(f"{base}/")
            link = page.get_by_role("link", name=WARNING, exact=True)
            assert link.count() == 1
            link.click()
            page.wait_for_url("**/captures?**")
            assert "failed=1" in page.url and "source=bahn.de" in page.url
            rows = page.locator("table tbody tr")
            assert rows.count() == 3
            for i in range(3):
                assert "bahn.de" in rows.nth(i).inner_text()

            page.goto(f"{base}/captures")
            bahn_row = page.locator("#source-health tr.source-row", has_text="bahn.de")
            assert bahn_row.locator("td").nth(2).inner_text().splitlines()[0] == "1.0.0"  # #1495: then the old-userscript chip

            _post(client, auth, tid, BAHN, 5, "1.0.0", [offer("89.90")])
            page.goto(f"{base}/")
            assert page.get_by_role("link", name=WARNING, exact=True).count() == 0
            assert page.locator(".source-warning").count() == 0
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
