"""The booking horizon per source and the first sales date of a trip (#2253, epic #2252)."""

from datetime import date

from app.models import Setting
from app.sales_open import HORIZON_KEY, horizons, sales_open_on


def test_sales_open_is_the_trip_date_minus_the_horizon():
    assert sales_open_on(date(2027, 6, 1), 180) == date(2026, 12, 3)


def test_no_horizon_gives_no_sales_date():
    assert sales_open_on(date(2027, 6, 1), None) is None


def test_horizons_keep_only_valid_whole_numbers(sessions):
    with sessions() as s:
        s.add(Setting(key=HORIZON_KEY.format(source="bahn.de"), value="180"))
        s.add(Setting(key=HORIZON_KEY.format(source="flixbus.com"), value=""))
        s.add(Setting(key=HORIZON_KEY.format(source="eurostar.com"), value="abc"))
        s.commit()
    with sessions() as s:
        assert horizons(s) == {"bahn.de": 180}
