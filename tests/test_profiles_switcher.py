"""The trip page has a profile switcher: `?profile=<id>` ranks with that profile; an unknown id gives the default (#231)."""

from decimal import Decimal

from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights
from tests.test_profiles_default import _first_is_direct
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

# offer("89.90"): 472 minutes, 1 transfer; direct("150.00"): 240 minutes, no transfer


def _profiles(sessions):
    """The default profile ranks the faster one first; the profile Cheap ranks the cheaper one first."""
    with sessions() as s:
        fast = ScoreProfile(name="Fast", is_default=True, config_json=to_config(Weights(hour_markup=Decimal("50"))))
        cheap = ScoreProfile(name="Cheap", config_json=to_config(Weights(hour_markup=Decimal("0"))))
        s.add_all([fast, cheap])
        s.commit()
        return cheap.id


def test_the_profile_of_the_url_ranks_the_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    cheap_id = _profiles(sessions)
    assert _first_is_direct(client.get(f"/trips/{trip_id}").text)
    page = client.get(f"/trips/{trip_id}", params={"profile": cheap_id}).text
    assert not _first_is_direct(page) and "= €99.90" in page


def test_a_url_weight_wins_over_the_chosen_profile(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    cheap_id = _profiles(sessions)
    page = client.get(f"/trips/{trip_id}", params={"profile": cheap_id, "hour_markup": "50"}).text
    assert "€150 price + €200 time = €350" in page and _first_is_direct(page)  # 240 min × 50/60


def test_an_unknown_profile_gives_the_default_ranking(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    _profiles(sessions)
    r = client.get(f"/trips/{trip_id}", params={"profile": 999999})
    assert r.status_code == 200 and _first_is_direct(r.text)


def test_the_switcher_lists_the_profiles_with_the_active_one_selected(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    cheap_id = _profiles(sessions)
    page = client.get(f"/trips/{trip_id}", params={"profile": cheap_id}).text
    assert f'<option value="{cheap_id}" selected>Cheap</option>' in page
    assert '<select name="profile">' in page and ">Fast</option>" in page
