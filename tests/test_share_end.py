"""The end date of the share link of a trip (#2026): the link stops after it, and the owner sets it."""

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models import Trip
from tests.test_share import _csrf, _setup, share
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _set_end(sessions, trip_id, day):
    with sessions() as s:
        s.get(Trip, trip_id).share_ends_on = day
        s.commit()


def _end_of(sessions, trip_id):
    with sessions() as s:
        return s.get(Trip, trip_id).share_ends_on


def _post_end(client, trip_id, value):
    return client.post(f"/trips/{trip_id}/share/end",
                       data={"csrf_token": _csrf(client, trip_id), "share_ends_on": value})


def test_a_link_stops_the_day_after_its_end_date(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    link = share(client, trip_id)
    anon = TestClient(app)
    _set_end(sessions, trip_id, _today() - timedelta(days=1))
    assert anon.get(link).status_code == 404
    assert anon.post(link + "/marks/1").status_code == 404
    for day in (_today(), _today() + timedelta(days=7)):
        _set_end(sessions, trip_id, day)
        assert anon.get(link).status_code == 200
    _set_end(sessions, trip_id, None)
    assert anon.get(link).status_code == 200


def test_the_owner_sets_and_clears_the_end_date(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    future = (_today() + timedelta(days=14)).isoformat()
    assert _post_end(client, trip_id, future).status_code == 200  # the redirect to the trip page
    assert _end_of(sessions, trip_id) == date.fromisoformat(future)
    assert _post_end(client, trip_id, "").status_code == 200  # the redirect to the trip page
    assert _end_of(sessions, trip_id) is None


def test_a_bad_or_past_end_date_gives_422_and_stores_nothing(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    kept = _today() + timedelta(days=3)
    _set_end(sessions, trip_id, kept)
    for value in ("abc", (_today() - timedelta(days=7)).isoformat()):
        assert _post_end(client, trip_id, value).status_code == 422
        assert _end_of(sessions, trip_id) == kept


def test_the_end_date_needs_the_csrf_token(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    kept = _today() + timedelta(days=3)
    _set_end(sessions, trip_id, kept)
    r = client.post(f"/trips/{trip_id}/share/end", data={"share_ends_on": ""})
    assert r.status_code == 403
    assert _end_of(sessions, trip_id) == kept


def test_new_link_keeps_the_end_date_and_revoke_clears_it(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    end = _today() + timedelta(days=5)
    _set_end(sessions, trip_id, end)
    share(client, trip_id)
    assert _end_of(sessions, trip_id) == end
    r = client.post(f"/trips/{trip_id}/share/revoke", data={"csrf_token": _csrf(client, trip_id)})
    assert r.status_code == 200
    assert _end_of(sessions, trip_id) is None


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0051")
    engine = create_engine(empty_database_url)
    try:
        assert "share_ends_on" in {c["name"] for c in inspect(engine).get_columns("trips")}
        command.downgrade(cfg, "0050")
        assert "share_ends_on" not in {c["name"] for c in inspect(engine).get_columns("trips")}
    finally:
        engine.dispose()
