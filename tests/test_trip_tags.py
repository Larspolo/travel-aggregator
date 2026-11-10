"""The tags of a trip in the create and edit forms (#1950)."""

from alembic import command
from sqlalchemy import create_engine, inspect, select

from app.models import Trip
from app.trips import trip_tags
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_booked import _alembic


def _save(c, trip_id, tags):
    data = {"title": "Ski", "origin_text": "Amsterdam", "destination_text": "Zürich", "travelers": "1",
            "status": "planning", "tags_text": tags}
    return c.post(f"/trips/{trip_id}/edit", data=data, headers={"X-CSRF-Token": _csrf(c, "/settings")},
                  follow_redirects=False)


def _tags(sessions, trip_id):
    with sessions() as s:
        return s.get(Trip, trip_id).tags_text


def test_trip_tags():
    assert trip_tags("work, , Zürich") == ["work", "Zürich"]
    assert trip_tags(None) == []


def test_the_form_stores_and_shows_the_tags_with_no_repeat(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    assert _save(c, trip_id, " work, Zürich, WORK , zurich, ").status_code == 303
    assert _tags(sessions, trip_id) == "work, Zürich"
    assert 'value="work, Zürich"' in c.get(f"/trips/{trip_id}/edit").text
    assert _save(c, trip_id, " ").status_code == 303
    assert _tags(sessions, trip_id) is None


def test_too_many_or_too_long_tags_give_422(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _save(c, trip_id, "a")
    r = _save(c, trip_id, "a, b, c, d, e, f")
    assert r.status_code == 422 and "at most 5 tags" in r.text
    r = _save(c, trip_id, "x" * 21)
    assert r.status_code == 422 and "a tag has at most 20 characters" in r.text
    assert _tags(sessions, trip_id) == "a"


def test_a_script_tag_shows_escaped(setup):  # noqa: F811
    c, _, trip_id = setup
    assert _save(c, trip_id, "<script>x</script>").status_code == 303
    page = c.get(f"/trips/{trip_id}/edit").text
    assert "<script>x</script>" not in page and "&lt;script&gt;x&lt;/script&gt;" in page


def test_the_copy_keeps_the_tags(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _save(c, trip_id, "work, summer 2027")
    h = {"X-CSRF-Token": _csrf(c, "/settings")}
    assert c.post(f"/trips/{trip_id}/copy", headers=h, follow_redirects=False).status_code == 303
    with sessions() as s:
        assert s.scalar(select(Trip).where(Trip.title.like("%(copy)"))).tags_text == "work, summer 2027"


def test_migration_0047_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("trips")}
        assert "tags_text" in cols()
        command.downgrade(cfg, "0046")
        assert "tags_text" not in cols()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
