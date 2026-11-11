"""The "Hour value" of a trip in the JSON export and import (#2422)."""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_forms import client, engine  # noqa: F401 (fixtures)
from tests.test_trip_leave_after import _new


def test_the_export_and_the_import_keep_the_hour_value(engine):  # noqa: F811
    tid = _new(engine, hour_value=Decimal("30.00"))
    with Session(engine) as s:
        data = trip_export(load_trip(s, tid))
        assert data["trip"]["hour_value"] == "30.00"
        new_id = import_trip(s, data).trip_id
        s.commit()
    with Session(engine) as s:
        assert s.get(Trip, new_id).hour_value == Decimal("30.00")


def test_an_export_without_the_key_imports_as_none(engine):  # noqa: F811
    tid = _new(engine, hour_value=Decimal("30.00"))
    with Session(engine) as s:
        data = trip_export(load_trip(s, tid))
        del data["trip"]["hour_value"]  # an older export
        new_id = import_trip(s, data).trip_id
        s.commit()
    with Session(engine) as s:
        assert s.get(Trip, new_id).hour_value is None


def test_an_export_with_a_value_of_101_is_an_invalid_file(engine):  # noqa: F811
    tid = _new(engine, hour_value=Decimal("30.00"))
    with Session(engine) as s:
        data = trip_export(load_trip(s, tid))
        data["trip"]["hour_value"] = "101"
        with pytest.raises(ValueError, match="not valid"):
            import_trip(s, data)
