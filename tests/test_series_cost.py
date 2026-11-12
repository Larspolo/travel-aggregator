"""The series page shows the effective cost of the best offer of each date (#2513), not its lowest price."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from tests.test_series_page import _series, client, engine  # noqa: F401 (fixtures)


def test_price_only_profile_shows_the_price(engine, client):  # noqa: F811
    sid, ids = _series(engine)
    with Session(engine) as s:
        profile = ScoreProfile(name="Price only", config_json=to_config(
            Weights(hour_markup=Decimal("0"), transfer_markup=Decimal("0"))))
        s.add(profile)
        s.flush()
        s.get(Trip, ids[0]).profile_id = profile.id
        s.commit()
    page = client.get(f"/series/{sid}").text
    assert page.count("effective €97.40") == 1 and page.count("no offers yet") == 3
