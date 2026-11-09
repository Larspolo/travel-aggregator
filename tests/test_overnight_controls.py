"""The overnight stop controls in "Advanced" (#1257): the trip page and the profile page."""

import re

from app.models import ScoreProfile
from app.profiles import from_config
from tests.test_ingest_best import setup  # noqa: F401 (fixture)
from tests.test_profile_edit import _post, client  # noqa: F401 (fixture)

NIGHT = [{"mode": "train", "carrier": "DB", "service_no": "ICE 1", "from_name": "Amsterdam Centraal",
          "to_name": "Köln Hbf", "depart_at": "2026-12-20T19:00:00+01:00", "arrive_at": "2026-12-20T23:40:00+01:00"},
         {"mode": "train", "carrier": "DB", "service_no": "ICE 2", "from_name": "Köln Hbf",
          "to_name": "Zürich HB", "depart_at": "2026-12-21T06:10:00+01:00", "arrive_at": "2026-12-21T11:00:00+01:00"}]
DAY = [{"mode": "train", "carrier": "DB", "service_no": "ICE 9", "from_name": "Amsterdam Centraal",
        "to_name": "Zürich HB", "depart_at": "2026-12-20T08:00:00+01:00", "arrive_at": "2026-12-20T18:00:00+01:00"}]


def _offer(price, legs):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": "Sparpreis", "legs": legs}


def test_the_fields_have_labels(client):  # noqa: F811
    page = client.get("/profiles/new").text
    assert re.search(r'Overnight stop: hotel cost \(€\)\s*<input[^>]*name="overnight_cost"', page)
    assert re.search(r'Overnight stop: minimum night minutes\s*<input[^>]*name="overnight_min"', page)


def test_a_hotel_cost_reranks_the_rows_and_shows_the_line(setup, sessions):  # noqa: F811
    setup([_offer("50.00", NIGHT), _offer("60.00", DAY)])
    from app.models import Trip
    with sessions() as s:
        trip_id = s.query(Trip).one().id
    from tests.test_ingest_best import TestClient, app  # the same app
    from app.auth import require_login
    app.dependency_overrides[require_login] = lambda: None
    try:
        c = TestClient(app)
        base = c.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0").text
        assert base.index("ICE 1") < base.index("ICE 9") and "overnight stop in Köln" not in base
        page = c.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0&overnight_cost=80").text
        assert page.index("ICE 9") < page.index("ICE 1")
        assert "overnight stop in Köln" in page
        assert 'name="overnight_cost"' in page and 'value="80"' in page
        assert c.get(f"/trips/{trip_id}?overnight_min=-1").status_code == 422
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_the_profile_page_keeps_both_values(client, sessions):  # noqa: F811
    r = _post(client, "/profiles/new", name="Hotel", overnight_cost="75", overnight_min="300")
    assert r.status_code == 303, r.text
    with sessions() as s:
        p = s.query(ScoreProfile).filter_by(name="Hotel").one()
        pid, w = p.id, from_config(p.config_json)
    assert (str(w.overnight_cost), w.overnight_min) == ("75", 300)
    page = client.get(f"/profiles/{pid}").text
    assert re.search(r'name="overnight_cost"[^>]*value="75"', page)
    assert re.search(r'name="overnight_min"[^>]*value="300"', page)


def test_a_negative_minimum_gives_the_form_error(client, sessions):  # noqa: F811
    r = _post(client, "/profiles/new", name="Bad", overnight_min="-1")
    assert r.status_code == 422 and "overnight_min" in r.text
    with sessions() as s:
        assert s.query(ScoreProfile).filter_by(name="Bad").count() == 0
