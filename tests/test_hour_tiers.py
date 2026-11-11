"""The hour tiers of the time cost (#1014): marginal, like tax brackets."""

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights, effective_cost

from tests.test_trip_hide import trip  # noqa: F401, E402

PASSWORD = "pw"
TIERS = dict(hour_markup=Decimal("4"), hour_tier1_after_min=240, hour_tier1_markup=Decimal("8"),
             hour_tier2_after_min=480, hour_tier2_markup=Decimal("15"))


def _time(minutes, **w):
    return effective_cost(Decimal("0"), minutes, 0, Weights(**w)).time_cost


def test_the_example_of_the_ticket():
    assert _time(600, **TIERS) == Decimal("78.00")
    assert _time(241, **TIERS) == Decimal("16.13")
    assert _time(240, **TIERS) == Decimal("16.00")


def test_the_order_of_the_tiers_does_not_matter():
    swapped = TIERS | dict(hour_tier1_after_min=480, hour_tier1_markup=Decimal("15"),
                           hour_tier2_after_min=240, hour_tier2_markup=Decimal("8"))
    for m in (0, 100, 241, 479, 600):
        assert _time(m, **swapped) == _time(m, **TIERS)


def test_no_tiers_or_one_tier():
    assert _time(90, hour_markup=Decimal("15")) == Decimal("22.50")
    assert _time(90, hour_markup=Decimal("15"), hour_tier2_markup=Decimal("99")) == Decimal("22.50")  # after 0: off
    assert _time(120, hour_markup=Decimal("10"), hour_tier2_after_min=60, hour_tier2_markup=Decimal("20")) == 30


def test_a_longer_trip_never_costs_less():
    costs = [_time(m, **TIERS) for m in range(0, 900, 7)]
    assert costs == sorted(costs)


def test_an_old_profile_loads_with_the_tiers_off():
    w = from_config({"hour_markup": "4"})
    assert (w.hour_tier1_after_min, w.hour_tier2_after_min) == (0, 0)
    assert from_config(to_config(Weights(**TIERS))) == Weights(**TIERS)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def test_the_trip_page_keeps_the_tiers_of_the_url(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"hour_tier1_after_min": 240, "hour_tier1_markup": "8",
                                                   "hour_tier2_after_min": 480, "hour_tier2_markup": "15"}).text
    assert 'name="hour_tier1_after_min" min="0" max="2880" step="1" value="240"' in page
    assert 'name="hour_tier2_markup" min="0" max="100" step="0.01" value="15"' in page
    assert "hour_tier2_after_min=480" in page  # the sort links keep the value


def test_a_saved_profile_keeps_the_tiers_and_the_list_names_them(client, sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Long", config_json=to_config(Weights(**TIERS))))
        s.commit()
    assert "€4/h · €8/h after 4 h · €15/h after 8 h" in client.get("/profiles").text
    with sessions() as s:
        p = s.scalars(select(ScoreProfile)).one()
        assert from_config(p.config_json).hour_tier2_markup == Decimal("15")
