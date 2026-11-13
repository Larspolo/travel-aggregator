"""The trip page has only the profile dropdown and the filters: the weights are set on the profile page (#2831)."""

import re

from tests.test_profiles_default import _first_is_direct
from tests.test_profiles_switcher import _profiles
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

GUARDS = ("app/web/templates/trip*.html", "app/web/pages.py")  # ship_pr runs this file for these changes (#730)
ADVANCED = ("airport_before_min", "night_hour_markup", "co2_price_kg", "carrier1_name", "weekday1_markup",
            "transfer_place1_name", "train_hour_markup", "stale_hours", "notice_markup")


def _inputs(page):
    return set(re.findall(r'<(?:input|select)[^>]*name="([^"]+)"', page))


def test_the_trip_page_has_no_weight_input_and_the_profile_links(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    _profiles(sessions)
    page = client.get(f"/trips/{trip_id}").text
    form = page[page.index('<form class="weights"'):page.index("</form>", page.index('<form class="weights"'))]
    names = _inputs(form)
    assert "hour_markup" not in names and "transfer_markup" not in names
    assert not names & set(ADVANCED)
    assert "profile" in names and "max_transfers" in names and "sort" in names
    assert 'class="advanced"' not in page and 'id="save-profile"' not in page and "Use profile" not in page
    assert "Profile and filters" in page and "Weights and filters" not in page
    assert re.search(r'href="/profiles/\d+">Edit profile</a>', page) and 'href="/profiles/new">New profile</a>' in page


def test_a_url_weight_still_ranks_and_stays_on_a_filter_change(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    cheap_id = _profiles(sessions)
    page = client.get(f"/trips/{trip_id}", params={"profile": cheap_id, "hour_markup": "40"}).text
    assert "€150 price + €160 time = €310" in page and _first_is_direct(page)  # 240 min × 40/60
    assert '<input type="hidden" name="hour_markup" value="40">' in page


def test_the_post_of_the_old_save_form_is_gone(trip):  # noqa: F811
    client, _, trip_id = trip
    assert client.post("/profiles", data={"trip_id": trip_id, "name": "X"}).status_code == 405


def test_the_htmx_answer_updates_the_profile_box(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    cheap_id = _profiles(sessions)
    part = client.get(f"/trips/{trip_id}", params={"profile": cheap_id}, headers={"HX-Request": "true"}).text
    box = part[part.index('id="profile-box"') - 30:]
    assert 'hx-swap-oob="true"' in box[:120] and "€0/h" in box
