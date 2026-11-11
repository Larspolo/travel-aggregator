"""The wait before the "arrive by" time of the trip in the effective cost (#1295)."""

import re
from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models import ScoreProfile, Trip
from app.profiles import from_config
from app.ranking import Weights
from app.timeofday import arrive_by_extras
from tests.test_ingest_best import setup  # noqa: F401 (fixture)
from tests.test_profile_edit import _post, client  # noqa: F401 (fixture)

W5 = Weights(wait_hour_markup=Decimal("5"))


def _it(arrive_utc, offset_min=60):
    leg = SimpleNamespace(arrive_at=arrive_utc, arrive_offset_min=offset_min)
    return SimpleNamespace(legs=[leg])


def test_an_early_arrival_costs_the_wait():
    it = _it(datetime(2026, 12, 20, 9, 30, tzinfo=timezone.utc))  # 10:30+01:00
    assert arrive_by_extras(it, time(14, 0), W5) == (("wait 3 h 30 min before 14:00", Decimal("17.50")),)


def test_no_part_at_or_after_the_time_with_no_time_or_with_0():
    at = datetime(2026, 12, 20, 13, 0, tzinfo=timezone.utc)  # 14:00+01:00
    assert arrive_by_extras(_it(at), time(14, 0), W5) == ()
    assert arrive_by_extras(_it(datetime(2026, 12, 20, 15, 0, tzinfo=timezone.utc)), time(14, 0), W5) == ()
    early = _it(datetime(2026, 12, 20, 9, 30, tzinfo=timezone.utc))
    assert arrive_by_extras(early, None, W5) == ()
    assert arrive_by_extras(early, time(14, 0), Weights()) == ()


EARLY = [{"mode": "train", "carrier": "DB", "service_no": "ICE 1", "from_name": "Amsterdam Centraal",
          "to_name": "Köln Hbf", "depart_at": "2026-12-20T07:00:00+01:00", "arrive_at": "2026-12-20T10:30:00+01:00"}]
LATE = [{"mode": "train", "carrier": "DB", "service_no": "ICE 9", "from_name": "Amsterdam Centraal",
         "to_name": "Köln Hbf", "depart_at": "2026-12-20T10:30:00+01:00", "arrive_at": "2026-12-20T14:00:00+01:00"}]


def _offer(price, legs):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": "Sparpreis", "legs": legs}


def test_the_trip_page_reranks_and_shows_the_line(setup, sessions):  # noqa: F811
    setup([_offer("50.00", EARLY), _offer("60.00", LATE)])
    with sessions() as s:
        trip = s.query(Trip).one()
        trip.arrive_by = time(14, 0)
        s.commit()
        trip_id = trip.id
    from tests.test_ingest_best import TestClient, app
    from app.auth import require_login
    app.dependency_overrides[require_login] = lambda: None
    try:
        c = TestClient(app)
        base = c.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0").text
        assert base.index("ICE 1") < base.index("ICE 9") and "wait 3 h 30 min" not in base
        page = c.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0&wait_hour_markup=5").text
        assert page.index("ICE 9") < page.index("ICE 1")
        assert "wait 3 h 30 min before 14:00" in page and "17.50" in page
        assert re.search(r'Wait before the arrival time, € per hour\s*<input[^>]*name="wait_hour_markup"[^>]*value="5"', page)
        assert c.get(f"/trips/{trip_id}?wait_hour_markup=-1").status_code == 422
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_the_profile_page_keeps_the_value(client, sessions):  # noqa: F811
    r = _post(client, "/profiles/new", name="Wait", wait_hour_markup="7.5")
    assert r.status_code == 303, r.text
    with sessions() as s:
        p = s.query(ScoreProfile).filter_by(name="Wait").one()
        pid, w = p.id, from_config(p.config_json)
    assert str(w.wait_hour_markup) == "7.5"
    assert re.search(r'name="wait_hour_markup"[^>]*value="7.5"', client.get(f"/profiles/{pid}").text)
