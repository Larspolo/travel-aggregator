"""The import page of the JSON export of a trip (#777)."""

import html
import json
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import make_password_hash
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Leg, Trip
from app.web.export import load_trip, trip_export

PASSWORD = "pw"


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


@pytest.fixture
def export(sessions):
    from datetime import datetime, timezone
    from decimal import Decimal
    utc = timezone.utc
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich",
                 date_from=date(2026, 12, 1), travelers=1, status="planning")
        it = Itinerary(fingerprint="x", mode_summary="train", depart_at=datetime(2026, 12, 1, 8, tzinfo=utc),
                       arrive_at=datetime(2026, 12, 1, 15, tzinfo=utc), duration_min=420, transfers=0)
        it.legs.append(Leg(seq=1, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                           to_name="Zürich", depart_at=it.depart_at, depart_offset_min=60, arrive_at=it.arrive_at,
                           arrive_offset_min=60))
        fare = Fare(source="bahn", fare_name="Sparpreis", latest_price=Decimal("79.90"), currency="EUR",
                    latest_captured_at=datetime(2026, 11, 4, tzinfo=utc))
        fare.prices.append(FarePrice(price=Decimal("79.90"), currency="EUR",
                                     captured_at=datetime(2026, 11, 4, tzinfo=utc)))
        it.fares.append(fare)
        t.itineraries.append(it)
        s.add(t)
        s.commit()
        data = trip_export(load_trip(s, t.id))
        s.delete(t)  # the import makes the trip again
        s.commit()
    return json.dumps(data).encode()


def _counts(sessions):
    with sessions() as s:
        return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Trip, Itinerary, Fare, FarePrice))


def _post(c, content, target="", token=None):
    files = {"file": ("trip.json", content, "application/json")} if content is not None else None
    data = {"target": target, "csrf_token": _token(c, "/trips/import") if token is None else token}
    return c.post("/trips/import", data=data, files=files, follow_redirects=False)


def _new_trip_id(r):
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_import_with_no_target_makes_a_trip(sessions, client, export):
    r = _post(client, export)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "Imported 1 itineraries, 1 fares and 1 prices; 0 unchanged" in html.unescape(page)
    assert "Imported" not in client.get(r.headers["location"]).text  # the message shows once
    assert _counts(sessions) == (1, 1, 1, 1)


def test_second_import_preselects_the_trip_and_adds_no_row(sessions, client, export):
    trip_id = _new_trip_id(_post(client, export))
    form = client.get("/trips/import").text
    key = html.unescape(re.search(rf'<option value="{trip_id}" data-match="([^"]*)"', form).group(1))
    t = json.loads(export)["trip"]
    assert json.loads(key) == [t["title"], t["origin"], t["destination"], t["date_from"], t["date_to"]]
    before = _counts(sessions)
    r = _post(client, export, target=str(trip_id))
    assert r.status_code == 303 and _new_trip_id(r) == trip_id
    assert "0 prices; 3 unchanged" in html.unescape(client.get(r.headers["location"]).text)
    assert _counts(sessions) == before


def test_no_login_goes_to_the_login_page(monkeypatch, export):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    r = TestClient(app).post("/trips/import", files={"file": ("t.json", export)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_no_csrf_token_is_forbidden(sessions, client, export):
    assert _post(client, export, token="").status_code == 403
    assert _counts(sessions) == (0, 0, 0, 0)


@pytest.mark.parametrize("content, message", [(b"not json", "The file is not JSON."),
                                              (b'{"format": "x"}', "export"),
                                              (None, "Select an export file.")])
def test_bad_file_shows_an_error_and_adds_no_row(sessions, client, content, message):
    r = _post(client, content)
    assert r.status_code == 400 and message in r.text
    assert _counts(sessions) == (0, 0, 0, 0)


def test_too_large_file_shows_an_error(sessions, client, monkeypatch):
    monkeypatch.setattr("app.web.trip_import.MAX_BODY_BYTES", 10)
    r = _post(client, b'{"a": "' + b"x" * 20 + b'"}')
    assert r.status_code == 400 and "larger than 10 bytes" in r.text


def test_trips_list_links_to_the_import_page(sessions, client):
    assert 'href="/trips/import"' in client.get("/").text


@pytest.mark.slow
def test_browser_preselects_the_trip_and_has_no_sideways_scroll(sessions, client, export, tmp_path):
    """The file input preselects the trip of a first import (trip_import.js); the form fits at 1280 and 390 px."""
    from playwright.sync_api import sync_playwright

    from app.auth import require_login
    from tests.test_all_pages_look import _launch, _serve

    trip_id = _new_trip_id(_post(client, export))
    path = tmp_path / "trip.json"
    path.write_bytes(export)
    app.dependency_overrides[require_login] = lambda: None
    srv, thread, base = _serve()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            for width in (1280, 390):
                page = browser.new_page(viewport={"width": width, "height": 800})
                page.goto(f"{base}/trips/import")
                assert page.input_value("#i-target") == ""
                page.set_input_files("#i-file", str(path))
                page.wait_for_function(f"document.getElementById('i-target').value === '{trip_id}'")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(tmp_path / f"trip-import-{width}.png"), full_page=True)
            browser.close()
    finally:
        srv.should_exit = True
        thread.join(5)
        app.dependency_overrides.pop(require_login, None)
