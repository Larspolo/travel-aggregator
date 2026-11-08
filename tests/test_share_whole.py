"""The whole share feature with a trip profile and an API token (#914, epic #902): the shared page ranks with the
profile of the trip, and it never shows an API token."""

import copy
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import hash_token
from app.main import app
from app.models import ApiToken, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from tests.test_share import share
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def timed(price, hours, service):
    """One leg from 09:00 that lasts `hours` hours, no transfer (as in tests/test_compare_tradeoff.py)."""
    o = copy.deepcopy(offer(price, service))
    o["legs"] = [dict(o["legs"][0], to_name="Zürich HB", depart_at="2026-12-20T09:00:00+01:00",
                      arrive_at=f"2026-12-20T{9 + hours:02d}:00:00+01:00")]
    return o


def _cheap_slow_and_dear_fast(client, auth, trip_id):
    # default hour markup 15 €/h: cheap 89.90 + 4 × 15 = 149.90; dear 119.90 + 3 × 15 = 164.90
    # hour markup 100 €/h: cheap 89.90 + 4 × 100 = 489.90; dear 119.90 + 3 × 100 = 419.90
    ingest(client, auth, trip_id, [timed("89.90", 4, "ICE 105"), timed("119.90", 3, "ICE 900")])


def _set_profile(sessions, trip_id, profile_id):
    with sessions() as s:
        s.get(Trip, trip_id).profile_id = profile_id
        s.commit()


def _shared_page(client, trip_id):
    link = share(client, trip_id)
    r = TestClient(app).get(link)
    assert r.status_code == 200
    return r.text


def test_the_shared_page_ranks_with_the_profile_of_the_trip(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _cheap_slow_and_dear_fast(client, auth, trip_id)
    with sessions() as s:
        s.add(ScoreProfile(name="Fast", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("100")))))
        s.commit()
        fast_id = s.scalars(select(ScoreProfile).where(ScoreProfile.name == "Fast")).one().id

    page = _shared_page(client, trip_id)
    assert page.index("€89.90") < page.index("€119.90")  # no profile: the default, the cheap one first

    _set_profile(sessions, trip_id, fast_id)
    page = _shared_page(client, trip_id)
    assert page.index("€119.90") < page.index("€89.90")  # the profile of the trip: the fast one first

    _set_profile(sessions, trip_id, None)
    page = _shared_page(client, trip_id)
    assert page.index("€89.90") < page.index("€119.90")  # the profile removed: the cheap one first again


def test_the_shared_page_shows_no_api_token(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _cheap_slow_and_dear_fast(client, auth, trip_id)
    with sessions() as s:
        token = tokens.create(s, "share-whole-token-name")
        token_hash = hash_token(token)
        assert s.scalars(select(ApiToken).where(ApiToken.token_hash == token_hash)).one()

    page = _shared_page(client, trip_id)
    assert "€89.90" in page  # the page did render the rows
    assert token not in page
    assert "share-whole-token-name" not in page
    assert token_hash not in page
