"""The box under the profile dropdown of the trip page shows the values of the active profile (#2830)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.test_profile_edit import client  # noqa: F401  (fixture)
from app.models import Fare, FarePrice, Itinerary, Leg, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights

D = Decimal


def _itinerary() -> Itinerary:
    depart = datetime(2030, 5, 1, 9, 0, tzinfo=timezone.utc)
    arrive = depart + timedelta(hours=2)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC1", from_name="A", to_name="B", depart_at=depart,
              depart_offset_min=0, arrive_at=arrive, arrive_offset_min=0)
    captured = datetime.now(timezone.utc)
    fare = Fare(source="manual", latest_price=D("50"), currency="EUR", latest_captured_at=captured,
                prices=[FarePrice(price=D("50"), currency="EUR", captured_at=captured)])
    return Itinerary(fingerprint="it1", depart_at=depart, arrive_at=arrive, duration_min=120, legs=[leg],
                     fares=[fare])


def _setup(sessions, *, default_weights=None, hour_value=None):
    with sessions() as s:
        s.add(ScoreProfile(name="Calm", is_default=True, config_json=to_config(default_weights or Weights())))
        s.add(ScoreProfile(name="Fast", config_json=to_config(Weights(hour_markup=D("42"), transfer_markup=D("7")))))
        trip = Trip(title="T", origin_text="A", destination_text="B", status="planning", hour_value=hour_value)
        trip.itineraries = [_itinerary()]  # the profile form shows only when the trip has rows
        s.add(trip)
        s.commit()
        return trip.id, {p.name: p.id for p in s.query(ScoreProfile).all()}


def _page(client, trip_id, profile=None):  # noqa: F811
    query = f"?profile={profile}" if profile else ""
    return client.get(f"/trips/{trip_id}{query}").text


def _box(html: str) -> str:
    start = html.index('id="profile-box"')
    return html[start:html.index("</div>", start)]


def test_box_shows_the_hour_and_transfer_values_of_the_active_profile(sessions, client):  # noqa: F811
    trip_id, ids = _setup(sessions)
    html = _page(client, trip_id, ids["Fast"])
    box = _box(html)
    assert "€42/h" in box
    assert "€7 per transfer" in box
    assert "(this trip)" not in box


def test_changing_the_profile_changes_the_box(sessions, client):  # noqa: F811
    trip_id, ids = _setup(sessions)
    calm = _box(_page(client, trip_id, ids["Calm"]))
    fast = _box(_page(client, trip_id, ids["Fast"]))
    assert "€15/h" in calm and "€42/h" in fast
    assert calm != fast


def test_other_settings_counts_the_fields_that_differ_from_the_defaults(sessions, client):  # noqa: F811
    trip_id, ids = _setup(sessions)
    assert "other settings" not in _box(_page(client, trip_id, ids["Calm"]))
    box = _box(_page(client, trip_id, ids["Fast"]))
    assert "0 other settings" not in box
    assert "other settings" not in box  # hour and transfer are shown above, not counted


def test_other_settings_counts_a_setting_outside_the_box(sessions, client):  # noqa: F811
    trip_id, ids = _setup(sessions, default_weights=Weights(baggage_fee=D("3")))
    box = _box(_page(client, trip_id, ids["Calm"]))
    assert "1 other settings" in box


def test_trip_hour_value_replaces_the_hour_markup(sessions, client):  # noqa: F811
    trip_id, ids = _setup(sessions, hour_value=D("30"))
    box = _box(_page(client, trip_id, ids["Fast"]))
    assert "€30.00/h (this trip)" in box
    assert "€42/h" not in box  # the trip value replaces it


def test_edit_link_opens_the_active_profile(sessions, client):  # noqa: F811
    trip_id, ids = _setup(sessions)
    box = _box(_page(client, trip_id, ids["Fast"]))
    assert f'href="/profiles/{ids["Fast"]}"' in box
