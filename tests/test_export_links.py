"""The "Export CSV" and "Export JSON" links in the "More" menu of the trip page (#702). A click downloads the file, at
1280 px and at 390 px. For a trip with offers from 2 sources, each fare is in each file with its latest price."""

import copy
import csv
import io
import json

import pytest

from app.web.export import CSV_COLUMNS
from tests.test_all_pages_look import _launch, _serve
from tests.test_ingest_api import BODY
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

BAHN = BODY["source"]
NS = "nsinternational.com"


def _download(page, name, dest):
    page.locator("details.more > summary").click()
    with page.expect_download() as info:
        page.get_by_role("link", name=name, exact=True).click()
    download = info.value
    download.save_as(dest)
    return download.suggested_filename


@pytest.mark.parametrize("width", [1280, 390])
def test_the_more_menu_downloads_the_csv_and_the_json(trip, tmp_path, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90")])
    server, thread, base = _serve()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            ctx = browser.new_context(accept_downloads=True, viewport={"width": width, "height": 844},
                                      has_touch=width == 390)
            page = ctx.new_page()
            page.goto(f"{base}/trips/{tid}")
            csv_name = _download(page, "Export CSV", str(tmp_path / "trip.csv"))
            page.goto(f"{base}/trips/{tid}")
            json_name = _download(page, "Export JSON", str(tmp_path / "trip.json"))
            ctx.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
    assert csv_name.endswith(".csv") and json_name.endswith(".json")
    assert (tmp_path / "trip.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert json.loads((tmp_path / "trip.json").read_text(encoding="utf-8"))["format"]


def test_each_fare_of_two_sources_has_its_latest_price_in_both_files(trip, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90")])
    ingest(client, auth, tid, [offer("84.50")])  # the latest bahn.de price of the same fare
    ns = copy.deepcopy(BODY)
    ns.update(source=NS, trip_id=tid, offers=[offer("95.00")])
    assert client.post("/api/ingest", json=ns, headers=auth).status_code == 200

    expected = {(BAHN, "Sparpreis", "84.50"), (NS, "Sparpreis", "95.00")}
    server, thread, base = _serve()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            ctx = browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 844})
            page = ctx.new_page()
            page.goto(f"{base}/trips/{tid}")
            _download(page, "Export CSV", str(tmp_path / "trip.csv"))
            page.goto(f"{base}/trips/{tid}")
            _download(page, "Export JSON", str(tmp_path / "trip.json"))
            ctx.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)

    text = (tmp_path / "trip.csv").read_bytes().decode("utf-8-sig")
    rows = [dict(zip(CSV_COLUMNS, row)) for row in csv.reader(io.StringIO(text, newline=""))][1:]
    in_csv = {(r["source"], r["fare_name"], r["latest_price"]) for r in rows}
    assert expected <= in_csv

    data = json.loads((tmp_path / "trip.json").read_text(encoding="utf-8"))
    in_json = {(f["source"], f["fare_name"], f["latest_price"])
               for it in data["itineraries"] for f in it["fares"]}
    assert expected <= in_json
