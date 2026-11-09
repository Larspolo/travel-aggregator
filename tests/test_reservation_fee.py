"""The reservation fee per leg in the effective cost (#1623, epic #1618): "Reservation € per leg" in "Advanced" adds
the fee for each leg of a fare with a mandatory reservation that its price does not include (`reservation_legs`)."""
from decimal import Decimal
from types import SimpleNamespace

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from app.risk import reservation_extras
from tests.test_carrier_settings_export import _csrf, _file, _only_profile
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def test_the_fee_per_leg_and_zero_adds_no_part():
    w = Weights(reservation_fee=Decimal("10"))
    assert reservation_extras(SimpleNamespace(reservation_legs=2), w) == (("reservation", Decimal("20")),)
    assert reservation_extras(SimpleNamespace(reservation_legs=0), w) == ()
    assert reservation_extras(SimpleNamespace(reservation_legs=2), Weights()) == ()


def _totals(page):
    return [line.rsplit("= €", 1)[1].split("<")[0].strip() for line in page.split("\n") if "= €" in line]


def test_the_breakdown_and_the_score_of_a_fare_with_a_reservation(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [reserved("required", None, None)])
    default = client.get(f"/trips/{trip_id}").text
    assert "reservation =" not in default and len(_totals(default)) == 1   # the fee €0: no part
    page = client.get(f"/trips/{trip_id}?reservation_fee=10").text
    assert f"€10 reservation = €{Decimal(_totals(default)[0]) + 10}" in page   # the score is €10 higher
    assert 'name="reservation_fee"' in page and 'value="10"' in page


def test_a_fare_with_no_reservation_does_not_change(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [reserved("included", None, None)])
    assert _totals(client.get(f"/trips/{trip_id}").text) == _totals(client.get(f"/trips/{trip_id}?reservation_fee=10").text)
    assert "€10 reservation" not in client.get(f"/trips/{trip_id}?reservation_fee=10").text


def test_the_settings_export_and_import_keep_the_fee(trip, sessions):  # noqa: F811
    client, _, _ = trip
    weights = Weights(reservation_fee=Decimal("12.50"))
    _only_profile(sessions, to_config(weights))
    export = client.get("/settings/export.json").json()
    assert export["profiles"][0]["config"]["reservation_fee"] == "12.50"
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    r = client.post("/settings/import", data={"csrf_token": _csrf(client, "/settings/import")},
                    files={"file": ("settings.json", _file(export, export["profiles"][0]["config"]),
                                    "application/json")})
    assert r.status_code == 200
    with sessions() as s:
        assert from_config(s.query(ScoreProfile).one().config_json) == weights
