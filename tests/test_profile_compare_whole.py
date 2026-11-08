"""One whole test of the best offer of each profile (#1212, epic #1205): a slow cheap offer and a fast expensive offer
come in through the ingest API, two profiles with other hour values find another best offer each on the trip page, and
a change of the hour value of one profile changes its line to the other offer."""

import copy
import re
from decimal import Decimal

from sqlalchemy import select

from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights
from tests.test_ingest_api import BODY
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)

DAY = "2026-12-20"


def _offer(price, depart, arrive, service):
    o = copy.deepcopy(BODY["offers"][0])
    o.update(price_amount=price, fare_name="Sparpreis", legs=[{
        "mode": "train", "carrier": "DB", "service_no": service, "from_name": "Amsterdam Centraal",
        "to_name": "Zürich HB", "depart_at": f"{DAY}T{depart}:00+01:00", "arrive_at": f"{DAY}T{arrive}:00+01:00"}])
    return o


def _ingest(client, auth, trip_id):
    """A slow cheap offer (07:00 → 19:00, 80 €) and a fast expensive offer (09:00 → 13:00, 150 €)."""
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=[
        _offer("80.00", "07:00", "19:00", "IC 1"),
        _offer("150.00", "09:00", "13:00", "ICE 2"),
    ])
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def _profiles(sessions):
    """Two profiles with other hour values: Cheap ignores the hours, Fast pays 50 € an hour."""
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("0")))))
        s.add(ScoreProfile(name="Fast", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("50")))))
        s.commit()
        return {p.name: p.id for p in s.scalars(select(ScoreProfile))}


def _line(page, profile_id):
    """The line of one profile in the 'Best by profile' section of the trip page."""
    section = re.search(r'<section class="profile-best card" id="profile-best">(.*?)</section>', page, re.S).group(1)
    return next(li for li in re.findall(r"<li>(.*?)</li>", section, re.S) if f"?profile={profile_id}" in li)


def test_each_profile_finds_its_own_best_offer_on_the_trip_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest(client, auth, trip_id)
    ids = _profiles(sessions)
    page = client.get(f"/trips/{trip_id}").text
    cheap = _line(page, ids["Cheap"])
    fast = _line(page, ids["Fast"])
    # Cheap: the 80 € offer (07:00) wins; Fast: 80 + 12 h × 50 € = 680 €, so the 150 + 4 h × 50 € = 350 € offer (09:00) wins
    assert "07:00" in cheap and "09:00" not in cheap
    assert "09:00" in fast and "07:00" not in fast
    assert "€80" in cheap and "€350" in fast


def test_a_changed_hour_value_changes_the_line_to_the_other_offer(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest(client, auth, trip_id)
    ids = _profiles(sessions)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)
    # Fast gets no hour value: 150 € (09:00) and 80 € (07:00) → the 80 € offer wins
    r = client.post(f"/profiles/{ids['Fast']}", data={"name": "Fast", "hour_markup": "0", "csrf_token": token},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    page = client.get(f"/trips/{trip_id}").text
    fast = _line(page, ids["Fast"])
    assert "07:00" in fast and "09:00" not in fast and "€80" in fast
    # the other profile keeps its own best offer
    cheap = _line(page, ids["Cheap"])
    assert "07:00" in cheap and "€80" in cheap
