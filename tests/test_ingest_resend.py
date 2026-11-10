"""A resend of the same capture is stored once (#1868, `capture:resend`): one capture per `capture_key` and token."""

import copy

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

from app import tokens
from app.main import app
from app.models import Capture, FarePrice, Trip
from tests.test_ingest_api import BODY

KEY = "7f0c1d2e-3a4b-4c5d-8e6f-0123456789ab"


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        one, two = tokens.create(s, "one"), tokens.create(s, "two")
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    return TestClient(app), {"Authorization": f"Bearer {one}"}, {"Authorization": f"Bearer {two}"}, trip_id


def _body(trip_id, **change):
    b = copy.deepcopy(BODY)
    b.update(trip_id=trip_id, **change)
    return b


def _counts(sessions):
    with sessions() as s:
        return (s.scalar(select(func.count()).select_from(Capture)),
                s.scalar(select(func.count()).select_from(FarePrice)))


def test_the_same_key_twice_gives_one_capture_and_the_first_answer(setup, sessions):
    client, auth, _, trip_id = setup
    first = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    second = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    assert first.status_code == second.status_code == 200
    assert first.json()["created"] == 1
    assert second.json() == first.json()
    assert _counts(sessions) == (1, 1)
    with sessions() as s:
        capture = s.scalar(select(Capture))
        assert capture.capture_key == KEY and capture.token_id is not None
        assert capture.answer_json == first.json()


def test_no_key_twice_gives_two_captures_as_before(setup, sessions):
    client, auth, _, trip_id = setup
    client.post("/api/ingest", json=_body(trip_id), headers=auth)
    second = client.post("/api/ingest", json=_body(trip_id), headers=auth)
    assert second.status_code == 200 and second.json()["unchanged"] == 1
    assert _counts(sessions) == (2, 1)  # an unchanged price adds no price row
    with sessions() as s:
        assert s.scalars(select(Capture.answer_json)).all() == [None, None]


def test_the_same_key_from_another_token_is_a_new_capture(setup, sessions):
    client, auth, other, trip_id = setup
    client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    second = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=other)
    assert second.status_code == 200 and second.json()["unchanged"] == 1
    assert _counts(sessions) == (2, 1)


def test_a_late_resend_adds_no_old_price_to_the_history(setup, sessions):
    """A resend that comes after a newer capture with another price: without the key it adds the old price again."""
    client, auth, _, trip_id = setup
    first = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    newer = _body(trip_id, captured_at="2026-11-03T20:00:00Z")
    newer["offers"][0]["price_amount"] = "79.90"
    client.post("/api/ingest", json=newer, headers=auth)
    resend = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    assert resend.json() == first.json()
    assert _counts(sessions) == (2, 2)


@pytest.mark.parametrize("key", ["short", "x" * 65, "has space in it 123", "ä" * 20, ""])
def test_a_bad_key_gets_422_and_stores_nothing(setup, sessions, key):
    client, auth, _, trip_id = setup
    r = client.post("/api/ingest", json=_body(trip_id, capture_key=key), headers=auth)
    assert r.status_code == 422
    assert _counts(sessions) == (0, 0)


def test_a_key_whose_first_post_has_no_answer_gets_409(setup, sessions):
    client, auth, _, trip_id = setup
    client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    with sessions() as s:
        s.execute(text("UPDATE captures SET answer_json = NULL"))
        s.commit()
    r = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    assert r.status_code == 409 and r.headers["Retry-After"] == "5"
    assert _counts(sessions) == (1, 1)


def test_migration_0045_up_and_down(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0044")
    engine = create_engine(empty_database_url)
    columns = text("SELECT column_name FROM information_schema.columns WHERE table_name = 'captures'")
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO trips (title, status) VALUES ('t', 'planning')"))
            conn.execute(text("INSERT INTO captures (trip_id, source, captured_at) "
                              "SELECT id, 'bahn.de', now() FROM trips"))
        command.upgrade(cfg, "0045")
        with engine.begin() as conn:
            row = conn.execute(text("SELECT token_id, capture_key, answer_json FROM captures")).one()
            assert tuple(row) == (None, None, None)
        command.downgrade(cfg, "0044")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM captures")).scalar() == 1
            assert {"token_id", "capture_key", "answer_json"}.isdisjoint(conn.execute(columns).scalars().all())
    finally:
        engine.dispose()
