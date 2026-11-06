"""A trip has its own score profile (#232): the trip page ranks with it, a deleted profile gives the default,
the edit form stores the choice and the migration 0009 upgrades and downgrades."""

from decimal import Decimal

from alembic import command
from sqlalchemy import create_engine, inspect, select

from app.models import ScoreProfile, Trip
from app.profiles import delete as delete_profile, to_config
from app.ranking import Weights
from tests.test_profiles_default import _first_is_direct
from tests.test_profiles_page import _token, client, two_profiles  # noqa: F401  (fixtures)
from tests.test_profiles_store import _alembic
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

# offer("89.90"): 472 minutes, 1 transfer; direct("150.00"): 240 minutes, no transfer


def _set_trip_profile(sessions, trip_id, profile_id):
    with sessions() as s:
        s.get(Trip, trip_id).profile_id = profile_id
        s.commit()


def _default_fast(sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Fast", is_default=True, config_json=to_config(Weights(hour_markup=Decimal("50")))))
        s.add(ScoreProfile(name="Cheap", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("0")))))
        s.commit()
        return {p.name: p.id for p in s.scalars(select(ScoreProfile))}


def test_a_trip_with_a_profile_ranks_with_it(trip, sessions):  # noqa: F811
    client_, auth, trip_id = trip
    ingest(client_, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _default_fast(sessions)
    assert _first_is_direct(client_.get(f"/trips/{trip_id}").text)  # no profile: the default one
    _set_trip_profile(sessions, trip_id, ids["Cheap"])
    assert not _first_is_direct(client_.get(f"/trips/{trip_id}").text)


def test_the_profile_of_the_url_wins_over_the_trip_profile(trip, sessions):  # noqa: F811
    client_, auth, trip_id = trip
    ingest(client_, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _default_fast(sessions)
    _set_trip_profile(sessions, trip_id, ids["Cheap"])
    assert _first_is_direct(client_.get(f"/trips/{trip_id}", params={"profile": ids["Fast"]}).text)


def test_deleting_the_profile_gives_the_trip_the_default(trip, sessions):  # noqa: F811
    client_, auth, trip_id = trip
    ingest(client_, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _default_fast(sessions)
    _set_trip_profile(sessions, trip_id, ids["Cheap"])
    with sessions() as s:
        assert delete_profile(s, ids["Cheap"])
    with sessions() as s:
        assert s.get(Trip, trip_id).profile_id is None
    assert _first_is_direct(client_.get(f"/trips/{trip_id}").text)


def test_the_edit_form_stores_and_shows_the_profile(client, sessions, two_profiles):  # noqa: F811
    with sessions() as s:
        t = Trip(title="Utrecht – Berlin")
        s.add(t)
        s.commit()
        trip_id = t.id
    path = f"/trips/{trip_id}/edit"
    assert f'<option value="{two_profiles["Cheap"]}">Cheap</option>' in client.get(path).text
    data = {"title": "Utrecht – Berlin", "travelers": "1", "status": "planning", "notes": "", "profile_id": str(two_profiles["Comfort"]),
            "csrf_token": _token(client, path)}
    r = client.post(path, data=data, follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        assert s.get(Trip, trip_id).profile_id == two_profiles["Comfort"]
    data["profile_id"] = "999999"
    r = client.post(path, data=data, follow_redirects=False)
    assert r.status_code == 422 and "no profile 999999" in r.text


def test_migration_0009_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "profile_id" in {c["name"] for c in inspect(engine).get_columns("trips")}
        command.downgrade(cfg, "-1")
        assert "profile_id" not in {c["name"] for c in inspect(engine).get_columns("trips")}
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
