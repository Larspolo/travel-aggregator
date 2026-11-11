"""The trip page shows the best offer of each profile (#1211): one line per profile with a link, and the mark
"(active)"; with one profile only, no section."""

import re
from decimal import Decimal

from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _profiles(sessions, both=True):
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=True, config_json=to_config(Weights(hour_markup=Decimal("2")))))
        if both:
            s.add(ScoreProfile(name="Comfort", config_json=to_config(Weights(hour_markup=Decimal("30")))))
        s.commit()
        return {p.name: p.id for p in s.query(ScoreProfile)}


def _section(page):
    m = re.search(r'<section class="profile-best card" id="profile-best">(.*?)</section>', page, re.S)
    return m.group(1) if m else None


def test_two_profiles_give_two_lines_with_links(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _profiles(sessions)
    section = _section(client.get(f"/trips/{trip_id}").text)
    assert section is not None and "Best by profile" in section
    lines = re.findall(r"<li>(.*?)</li>", section, re.S)
    assert len(lines) == 2
    assert f'href="?profile={ids["Cheap"]}">Cheap</a> <strong>(active)</strong>' in lines[0]
    assert "train" in lines[0] and "€115.63" in lines[0]  # 89.90 + 472 min × €2/h + €10 transfer
    assert f'href="?profile={ids["Comfort"]}">Comfort</a>' in lines[1] and "(active)" not in lines[1]
    assert "€270" in lines[1]  # 150 + 4 h × €30
    other = _section(client.get(f"/trips/{trip_id}", params={"profile": ids["Comfort"]}).text)
    assert "Comfort</a> <strong>(active)</strong>" in other and "Cheap</a> <strong>" not in other


def test_one_profile_gives_no_section(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    _profiles(sessions, both=False)
    page = client.get(f"/trips/{trip_id}").text
    assert "Best by profile" not in page
