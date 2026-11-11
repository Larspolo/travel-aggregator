"""The sources that give the best offers (#1940): `source_wins()` counts the trips of each source and the trips in
which its fare is the main fare of the best offer by the default profile."""
import copy
from datetime import datetime, timezone
from decimal import Decimal

from app.models import Capture, Itinerary, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from app.source_wins import SourceWins, source_wins
from tests.test_ingest_api import BODY
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def _ingest(client, auth, trip_id, source, offers, at="2026-11-03T19:41:00Z"):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=offers, captured_at=at)
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _trip(sessions, profile_id=None):
    with sessions() as s:
        t = Trip(title="B", origin_text="Amsterdam", destination_text="Zürich", profile_id=profile_id)
        s.add(t)
        s.commit()
        return t.id


def _wins(sessions):
    with sessions() as s:
        return source_wins(s, NOW)


def test_each_source_wins_one_of_two_trips(trip, sessions):  # noqa: F811
    client, auth, t1 = trip
    t2 = _trip(sessions)
    _ingest(client, auth, t1, "bahn.de", [offer("80.00")])
    _ingest(client, auth, t1, "trainline", [offer("90.00", "ICE 9")])
    _ingest(client, auth, t2, "bahn.de", [offer("95.00")])
    _ingest(client, auth, t2, "trainline", [offer("85.00", "ICE 9")])
    assert _wins(sessions) == [SourceWins("bahn.de", 1, 2), SourceWins("trainline", 1, 2)]


def test_a_hidden_itinerary_does_not_count(trip, sessions):  # noqa: F811
    client, auth, t1 = trip
    _ingest(client, auth, t1, "bahn.de", [offer("80.00")])
    _ingest(client, auth, t1, "trainline", [offer("90.00", "ICE 9")])
    with sessions() as s:
        s.query(Itinerary).filter(Itinerary.trip_id == t1, Itinerary.fares.any(source="bahn.de")).update(
            {"hidden": True}, synchronize_session=False)
        s.commit()
    assert _wins(sessions) == [SourceWins("trainline", 1, 1), SourceWins("bahn.de", 0, 1)]


def test_one_itinerary_with_two_sources_counts_for_its_main_fare(trip, sessions):  # noqa: F811
    client, auth, t1 = trip
    _ingest(client, auth, t1, "bahn.de", [offer("80.00")])
    _ingest(client, auth, t1, "trainline", [offer("90.00")])  # the same train: one itinerary, two fares
    with sessions() as s:
        assert s.query(Itinerary).filter_by(trip_id=t1).count() == 1
    assert _wins(sessions) == [SourceWins("bahn.de", 1, 1), SourceWins("trainline", 0, 1)]


def test_old_captures_and_trips_with_no_offer(trip, sessions):  # noqa: F811
    client, auth, t1 = trip
    _ingest(client, auth, t1, "bahn.de", [offer("80.00")], at="2025-11-01T10:00:00Z")
    t2 = _trip(sessions)
    with sessions() as s:
        s.add(Capture(trip_id=t2, source="trainline", captured_at=datetime(2026, 11, 1, tzinfo=timezone.utc)))
        s.commit()
    assert _wins(sessions) == [SourceWins("trainline", 0, 1)]


def test_the_default_profile_wins_over_the_profile_of_the_trip(trip, sessions):  # noqa: F811
    client, auth, _ = trip
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=True, config_json=to_config(Weights(hour_markup=Decimal("2")))))
        comfort = ScoreProfile(name="Comfort", is_default=False,
                               config_json=to_config(Weights(hour_markup=Decimal("30"))))
        s.add(comfort)
        s.commit()
        comfort_id = comfort.id
    t2 = _trip(sessions, comfort_id)
    _ingest(client, auth, t2, "bahn.de", [offer("89.90")])  # slow and cheap: best for Cheap
    _ingest(client, auth, t2, "trainline", [direct("150.00")])  # fast: best for Comfort
    assert _wins(sessions) == [SourceWins("bahn.de", 1, 1), SourceWins("trainline", 0, 1)]
