"""The page "Travel per year" shows the CO₂ of the booked journeys (#1465)."""

from app.models import ScoreProfile
from tests.test_spend_page import add, client, text  # noqa: F401  (client is a fixture)


def _profile(sessions, flight_kg_h):
    with sessions() as s:
        s.add(ScoreProfile(name="Holiday", is_default=True, config_json={"co2_flight_kg_h": flight_kg_h}))
        add(s, 1, 2026, "flight", 120, "100")
        s.commit()


def test_a_booked_flight_of_two_hours_shows_its_co2_and_the_note(client, sessions):  # noqa: F811
    _profile(sessions, "90")
    page = text(client.get("/upcoming/years").text)
    assert "2 h · about 180 kg CO₂" in page  # the year line
    assert page.count("about 180 kg CO₂") == 2  # the year line and the mode line
    assert "CO₂ per traveler, estimated with the kg per hour of the profile Holiday." in page


def test_the_kg_per_flight_hour_of_the_profile_changes_the_value(client, sessions):  # noqa: F811
    _profile(sessions, "50")
    page = text(client.get("/upcoming/years").text)
    assert "about 100 kg CO₂" in page and "180 kg" not in page


def test_no_co2_part_with_0_kg(client, sessions):  # noqa: F811
    _profile(sessions, "0")
    assert "kg CO₂" not in text(client.get("/upcoming/years").text)
