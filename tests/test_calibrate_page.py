"""The hour value of the bookings on the profile page and "Use this hour value" (#1711, epic #1708)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from app.web.pages import fit_hour_value
from tests.test_calibrate_bookings import BOOKED_AT, _booked, _it, _trip
from tests.test_profile_edit import _token, client  # noqa: F401  (fixture)

D = Decimal


@pytest.fixture
def profile(sessions):
    with sessions() as s:
        p = ScoreProfile(name="Mine", config_json=to_config(Weights(hour_markup=D("10"))))
        s.add(p)
        s.commit()
        return p.id


def two_bookings(sessions):
    _trip(sessions, _booked(), _it("other", 3, [("100", BOOKED_AT - timedelta(days=1))]))
    _trip(sessions, _booked("slow", hours=4, price="60"), _it("fast", 3, [("100", BOOKED_AT - timedelta(days=1))]))


def _hour(sessions, pid):
    with sessions() as s:
        return from_config(s.get(ScoreProfile, pid).config_json).hour_markup


def test_the_two_bookings_fit_20_to_40_and_the_button_stores_30(client, sessions, profile):  # noqa: F811
    two_bookings(sessions)
    page = client.get(f"/profiles/{profile}").text
    assert "Your bookings fit an hour value from €20 to €40 (2 of 2 bookings)" in page
    r = client.post(f"/profiles/{profile}/hour-value", data={"csrf_token": _token(client, f"/profiles/{profile}"),
                                                             "hour_markup": "99"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/profiles/{profile}"
    assert _hour(sessions, profile) == D("30.00")
    assert 'value="30.00"' in client.get(f"/profiles/{profile}").text


def test_no_booking_shows_no_button(client, profile):  # noqa: F811
    page = client.get(f"/profiles/{profile}").text
    assert "No bookings to compare yet" in page and "Use this hour value" not in page


def test_an_open_interval_shows_one_end(client, sessions, profile):  # noqa: F811
    _trip(sessions, _booked(), _it("other", 3, [("100", BOOKED_AT - timedelta(days=1))]))
    assert "Your bookings fit an hour value from €20 (1 of 1 bookings)" in client.get(f"/profiles/{profile}").text


def test_no_csrf_is_403_and_changes_nothing(client, sessions, profile):  # noqa: F811
    two_bookings(sessions)
    assert client.post(f"/profiles/{profile}/hour-value", follow_redirects=False).status_code == 403
    assert _hour(sessions, profile) == D("10")


def test_an_unknown_profile_is_404(client):  # noqa: F811
    r = client.post("/profiles/9999/hour-value", data={"csrf_token": _token(client, "/profiles/new")})
    assert r.status_code == 404


@pytest.mark.parametrize("fit, value", [((D("20"), D("40"), 2, 2), D("30.00")), ((D("20"), None, 1, 1), D("20.00")),
                                        ((None, D("40"), 1, 1), D("40.00")), ((D("150"), None, 1, 1), D("100.00")),
                                        ((None, D("-5"), 1, 1), D("0.00")), ((D("1.005"), D("2"), 1, 1), D("1.50"))])
def test_the_value_of_an_interval(fit, value):
    assert fit_hour_value(fit) == value
