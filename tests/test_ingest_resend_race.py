"""A resend while the first POST runs gets 409; after a first POST that failed, 200 with its stored result (#1869)."""

import threading

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app import ingest
from tests.test_ingest_resend import KEY, _body, _counts, setup  # noqa: F401 (the fixture)


def test_a_resend_while_the_first_post_runs_gets_409_and_the_first_gets_200(setup, sessions, monkeypatch):  # noqa: F811
    client, auth, _, trip_id = setup
    stored, go = threading.Event(), threading.Event()
    upsert = ingest.upsert_offers

    def slow_upsert(*args, **kwargs):  # the first POST waits after the commit of its capture, before its answer
        stored.set()
        assert go.wait(30)
        return upsert(*args, **kwargs)

    monkeypatch.setattr(ingest, "upsert_offers", slow_upsert)
    first = {}
    thread = threading.Thread(target=lambda: first.update(
        r=client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)))
    thread.start()
    try:
        assert stored.wait(30)
        second = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    finally:
        go.set()
        thread.join(30)
    assert second.status_code == 409 and second.headers["Retry-After"] == "5"
    assert first["r"].status_code == 200 and first["r"].json()["created"] == 1
    assert _counts(sessions) == (1, 1)
    again = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    assert again.status_code == 200 and again.json() == first["r"].json()


def test_the_unique_insert_of_a_second_post_gets_409_and_no_capture(setup, sessions, monkeypatch):  # noqa: F811
    """Two POSTs that both find no capture of the key: the insert of the second fails on the constraint."""
    client, auth, _, trip_id = setup
    client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    monkeypatch.setattr(ingest, "find_resend", lambda *args: None)
    r = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    assert r.status_code == 409 and r.headers["Retry-After"] == "5"
    assert _counts(sessions) == (1, 1)


def _first_without_answer(client, auth, trip_id, sessions, age):
    client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    with sessions() as s:
        s.execute(text("UPDATE captures SET answer_json = NULL, received_at = now() - make_interval(secs => :age)"),
                  {"age": age})
        s.commit()


def test_a_running_first_post_younger_than_60_seconds_gives_409(setup, sessions):  # noqa: F811
    client, auth, _, trip_id = setup
    _first_without_answer(client, auth, trip_id, sessions, 30)
    r = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    assert r.status_code == 409
    assert _counts(sessions) == (1, 1)


def test_a_failed_first_post_older_than_60_seconds_gives_200_with_the_warning(setup, sessions):  # noqa: F811
    client, auth, _, trip_id = setup
    _first_without_answer(client, auth, trip_id, sessions, 90)
    r = client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth)
    assert r.status_code == 200
    answer = r.json()
    assert answer["warning"] == ingest.FAILED_SEND
    assert (answer["created"], answer["updated"], answer["unchanged"], answer["trip_id"]) == (0, 0, 0, trip_id)
    assert answer["trip_title"] == "Amsterdam – Zürich" and answer["best"] is None
    assert _counts(sessions) == (1, 1)
    assert client.post("/api/ingest", json=_body(trip_id, capture_key=KEY), headers=auth).json() == answer


def test_migration_0046_up_and_down(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0045")
    engine = create_engine(empty_database_url)
    columns = text("SELECT column_name FROM information_schema.columns WHERE table_name = 'captures'")
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO trips (title, status) VALUES ('t', 'planning')"))
            conn.execute(text("INSERT INTO captures (trip_id, source, captured_at) "
                              "SELECT id, 'bahn.de', now() FROM trips"))
        command.upgrade(cfg, "0046")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT received_at FROM captures")).scalar() is not None
        command.downgrade(cfg, "0045")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM captures")).scalar() == 1
            assert "received_at" not in conn.execute(columns).scalars().all()
    finally:
        engine.dispose()


@pytest.mark.parametrize("name, race", [("uq_captures_token_key", True), ("uq_itineraries_trip_fingerprint", False)])
def test_only_the_key_constraint_is_a_resend_race(name, race):
    class Diag:
        constraint_name = name

    class Orig:
        diag = Diag()

    assert ingest._is_resend_race(ingest.IntegrityError("x", {}, Orig())) is race
