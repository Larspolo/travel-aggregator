"""The weekday markups: the local weekday of the first departure adds its markup to the cost (#2136)."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models import ScoreProfile
from app.profiles import from_config
from app.ranking import Weights
from app.timeofday import weekday_extras
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _it(at, offset_min=60):
    return SimpleNamespace(legs=[SimpleNamespace(depart_at=at, depart_offset_min=offset_min)])


FRIDAY_2230 = datetime(2026, 12, 4, 22, 30, tzinfo=timezone.utc)  # local Friday 23:30
FRIDAY_2330 = datetime(2026, 12, 4, 23, 30, tzinfo=timezone.utc)  # local Saturday 00:30


def test_the_local_weekday_of_the_first_leg_gives_the_part():
    w = Weights(weekday5_markup=Decimal("15"))
    assert weekday_extras(_it(FRIDAY_2230), w) == (("Friday", Decimal("15")),)
    assert weekday_extras(_it(FRIDAY_2330), w) == ()


def test_all_markups_zero_give_no_part_and_a_negative_markup_is_a_discount():
    assert weekday_extras(_it(FRIDAY_2230), Weights()) == ()
    assert weekday_extras(_it(FRIDAY_2330), Weights(weekday6_markup=Decimal("-5"))) == (("Saturday", Decimal("-5")),)
    assert weekday_extras(SimpleNamespace(legs=[]), Weights(weekday5_markup=Decimal("15"))) == ()


def test_the_form_shows_and_saves_the_values(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("100.00", "FR 1")])
    page = client.get(f"/trips/{trip_id}?weekday5_markup=15").text
    assert 'name="weekday5_markup" min="-1000" max="1000" step="0.01" value="15"' in page and "Sunday markup" in page
    assert client.get(f"/trips/{trip_id}?weekday1_markup=5000").status_code == 422
    data = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id, "name": "Days", "weekday5_markup": "15",
            "weekday7_markup": "-5.50"}
    assert client.post("/profiles", data=data, follow_redirects=False).status_code == 303
    with sessions() as s:
        w = from_config(s.query(ScoreProfile).one().config_json)
    assert (str(w.weekday5_markup), str(w.weekday7_markup), w.weekday1_markup) == ("15", "-5.50", Decimal("0"))
