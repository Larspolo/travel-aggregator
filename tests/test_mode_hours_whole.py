"""The hour value per mode (#1567) in the break-even (#892) and in the settings export and import (#1566)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from app.tradeoff import break_even
from app.web.pages import row_cost
from tests.test_carrier_settings_export import _csrf, _file, _only_profile
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)

T0 = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


def _leg(mode, hours):
    return SimpleNamespace(mode=mode, depart_at=T0, arrive_at=T0 + timedelta(hours=hours),
                           from_name="A", to_name="B", carrier="")


def _fare(price):
    return SimpleNamespace(id=1, latest_price=Decimal(price), currency="EUR", flexibility=None, travel_class=None,
                           self_transfers=0, checked_bags_included=0, checked_bag_price=None, source="test",
                           latest_captured_at=T0, seen_price=None, name="f", default=False)


def _total(mode, hours, price, weights):
    it = SimpleNamespace(legs=[_leg(mode, hours)], duration_min=int(hours * 60), transfers=0,
                         mode_summary=mode, trip=SimpleNamespace(travelers=1, arrive_by=None))
    return row_cost(it, [_fare(price)], [], weights, T0)[1].total


def test_the_break_even_with_a_train_hour_value_is_twenty_euro_by_hand():
    # The train: €60 + 4 h × (5 − h) + 4 h × h = €80 at every hour markup. The flight: €40 + 2 h × h.
    # They are equal at h = 20, and the flight is better below it.
    base = dict(hour_markup=Decimal("15"), airport_before_min=0, airport_after_min=0, train_hour_markup=Decimal("5"))
    h = Decimal("15")
    a_now = _total("flight", 2, "40", Weights(**base))
    a_next = _total("flight", 2, "40", Weights(**{**base, "hour_markup": h + 1}))
    x_now = _total("train", 4, "60", Weights(**base))
    x_next = _total("train", 4, "60", Weights(**{**base, "hour_markup": h + 1}))
    assert (a_now, a_next, x_now, x_next) == (Decimal("70"), Decimal("72"), Decimal("80"), Decimal("80"))
    be = break_even(a_now, a_next, x_now, x_next, h)
    assert be is not None and be.hour_value == Decimal("20.00") and be.better == "above"


def test_an_export_and_an_import_keep_the_four_values_and_none(trip, sessions):  # noqa: F811
    client, _, _ = trip
    weights = Weights(train_hour_markup=Decimal("5"), bus_hour_markup=None, flight_hour_markup=Decimal("30"),
                      ferry_hour_markup=None)
    _only_profile(sessions, to_config(weights))
    export = client.get("/settings/export.json").json()
    config = export["profiles"][0]["config"]
    assert config["train_hour_markup"] == "5" and config["bus_hour_markup"] is None
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    r = client.post("/settings/import", data={"csrf_token": _csrf(client, "/settings/import")},
                    files={"file": ("settings.json", _file(export, config), "application/json")})
    assert r.status_code == 200 and "imported" in r.text
    with sessions() as s:
        rows = s.query(ScoreProfile).all()
        assert len(rows) == 1 and from_config(rows[0].config_json) == weights
