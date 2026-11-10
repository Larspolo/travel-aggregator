"""The places that use a best offer skip the departed offers: the departure days, the round-trip grid, the split tickets
and "Best by profile" (#1403, epic #1390). The offers depart relative to the real time, because the days, the grid, the
split and `best_by_profile()` read `datetime.now()`."""

import copy
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Fare, Itinerary, Leg, ScoreProfile, Trip
from app.profile_compare import best_by_profile
from app.profiles import to_config
from app.ranking import Weights
from tests.test_ingest_api import BODY
from tests.test_return_grid_whole import _page_cells
from tests.test_reparse import setup  # noqa: F401  (fixture: logged-in client, #1179)
from tests.test_split_page import _split
from tests.test_trip_book_timing import without_book_timing
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
# the departed offer left yesterday at noon (UTC); the later offers depart tomorrow and the day after
YESTERDAY = (NOW - timedelta(days=1)).replace(hour=12, minute=0)
TOMORROW = YESTERDAY + timedelta(days=2)
DAY_AFTER = TOMORROW + timedelta(days=1)


def _offer(price, service, depart):
    """A one-leg offer of 2 hours: the offers have the same length, so the cheapest one is the best one."""
    o = copy.deepcopy(BODY["offers"][0])
    o.update(price_amount=price, fare_name="Sparpreis", legs=[{
        "mode": "train", "carrier": "DB", "service_no": service, "from_name": "Amsterdam Centraal",
        "to_name": "Zürich HB", "depart_at": depart.isoformat(), "arrive_at": (depart + timedelta(hours=2)).isoformat()}])
    return o


def _part(s, trip_id, frm, to, depart, hours, price, source):
    """A split part (one leg) with a fare of `source`, stored as the split tests store it."""
    arrive = depart + timedelta(hours=hours)
    it = Itinerary(trip_id=trip_id, fingerprint=f"{frm}{to}{depart.isoformat()}{source}", mode_summary="train",
                   depart_at=depart, arrive_at=arrive, duration_min=int(hours * 60), transfers=0)
    it.legs = [Leg(seq=0, mode="train", from_name=frm, to_name=to, depart_at=depart, depart_offset_min=60,
                   arrive_at=arrive, arrive_offset_min=60)]
    it.fares = [Fare(source=source, latest_price=Decimal(price), currency="EUR", latest_captured_at=NOW)]
    s.add(it)


def test_the_days_show_no_departed_offer(trip, monkeypatch):  # noqa: F811
    import app.departed
    monkeypatch.setattr(app.departed, "clock", lambda: NOW)  # the trip page hides the offers with this clock (#1391)
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_offer("40.00", "ICE 1", YESTERDAY), _offer("70.00", "ICE 2", TOMORROW),
                                   _offer("75.00", "ICE 3", DAY_AFTER)])
    page = without_book_timing(client.get(f"/trips/{trip_id}").text)
    assert f"day={TOMORROW.date()}" in page and f"day={DAY_AFTER.date()}" in page
    assert f"day={YESTERDAY.date()}" not in page
    assert "€40.00" not in page


def test_the_round_trip_grid_uses_no_departed_outbound_offer(trip, sessions, monkeypatch):  # noqa: F811
    import app.departed
    monkeypatch.setattr(app.departed, "clock", lambda: NOW)  # the days of the outbound page use this clock (#1391)
    client, auth, out_id = trip
    with sessions() as s:
        back = Trip(title="Zürich – Amsterdam", origin_text="Zürich", destination_text="Amsterdam", return_of_id=out_id)
        s.add(back)
        s.flush()
        back_id = back.id
        out = s.get(Trip, out_id)
        out.date_from, out.date_to = YESTERDAY.date(), DAY_AFTER.date()
        back.date_from, back.date_to = TOMORROW.date(), DAY_AFTER.date()
        s.commit()
    ingest(client, auth, out_id, [_offer("50.00", "ICE 1", YESTERDAY), _offer("80.00", "ICE 2", TOMORROW)])
    ingest(client, auth, back_id, [_offer("40.00", "ICE 11", TOMORROW), _offer("66.00", "ICE 12", DAY_AFTER)])
    html = client.get(f"/trips/{out_id}").text
    cells, best = _page_cells(html)
    grid = re.search(r'<details class="card return-grid".*?</details>', html, re.S).group(0)
    assert "€50" not in grid
    yesterday, tomorrow = YESTERDAY.strftime("%d-%m"), TOMORROW.strftime("%d-%m")
    assert all(v == "—" for (row, _), v in cells.items() if row == yesterday)
    assert cells[(tomorrow, tomorrow)] != "—"
    assert best is not None and best[0] == tomorrow


def test_the_split_pair_uses_no_departed_first_part(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    a, b = _split(c, sessions, trip_id)
    with sessions() as s:
        # the departed first part (cheap) ends one hour ago; the later first part ends in 1 h 30 min
        _part(s, a, "Amsterdam", "Köln", NOW - timedelta(hours=2), 1, "40", "ns")
        _part(s, a, "Amsterdam", "Köln", NOW + timedelta(minutes=30), 1, "60", "ict")
        _part(s, b, "Köln", "Zürich", NOW + timedelta(hours=2, minutes=30), 5, "50", "db")
        s.commit()
    section = c.get(f"/trips/{trip_id}").text
    section = section[section.index("Split tickets via Köln"):]
    assert "(ict)" in section and "(ns)" not in section


def test_best_by_profile_gives_no_departed_offer(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_offer("40.00", "ICE 1", YESTERDAY), _offer("90.00", "ICE 2", TOMORROW)])
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=True, config_json=to_config(Weights(hour_markup=Decimal("2")))))
        s.add(ScoreProfile(name="Comfort", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("30")))))
        s.commit()
        results = best_by_profile(s, s.get(Trip, trip_id))
    assert [r.profile.name for r in results] == ["Cheap", "Comfort"]
    for r in results:
        assert r.itinerary is not None and r.fare is not None
        assert r.fare.latest_price == Decimal("90.00")
        assert r.itinerary.depart_at.date() == TOMORROW.date()
