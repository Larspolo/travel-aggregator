"""The "Checked bag" of a trip in the JSON export and import (#2399)."""

from sqlalchemy.orm import Session

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_forms import client, engine  # noqa: F401 (fixtures)
from tests.test_trip_leave_after import _new


def test_the_export_and_the_import_keep_none(engine):  # noqa: F811
    tid = _new(engine, checked_bag="none")
    with Session(engine) as s:
        data = trip_export(load_trip(s, tid))
        assert data["trip"]["checked_bag"] == "none"
        new_id = import_trip(s, data).trip_id
        s.commit()
    with Session(engine) as s:
        assert s.get(Trip, new_id).checked_bag == "none"


def test_an_export_without_the_key_imports_as_the_profile(engine):  # noqa: F811
    tid = _new(engine, checked_bag="none")
    with Session(engine) as s:
        data = trip_export(load_trip(s, tid))
        del data["trip"]["checked_bag"]  # an older export
        new_id = import_trip(s, data).trip_id
        s.commit()
    with Session(engine) as s:
        assert s.get(Trip, new_id).checked_bag is None
