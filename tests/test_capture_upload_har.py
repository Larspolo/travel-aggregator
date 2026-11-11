"""Upload a HAR file on the captures page of a trip (#1563)."""

import json

from sqlalchemy import select

from app.models import Capture
from app.schemas import MAX_HAR_BYTES
from tests import test_capture_upload as base
from tests.test_capture_upload import _count, _post
from tests.test_har_read import bahn_entry, entry, har

client = base.client
trip_id = base.trip_id


def _har():
    return json.dumps(har(bahn_entry("fahrplan-amsterdam-berlin.json"),
                          entry("https://www.bahn.de/logo.png", text="iVBOR", mime="image/png"),
                          bahn_entry("fahrplan-koeln-muenchen.json"))).encode()


def test_har_upload_stores_each_search_entry(client, sessions, trip_id):
    r = _post(client, trip_id, source="", content=_har(), name="session.har")
    assert r.status_code == 303
    assert r.headers["location"] == f"/trips/{trip_id}/captures?har=2"
    with sessions() as s:
        caps = s.scalars(select(Capture).where(Capture.trip_id == trip_id)).all()
        assert [c.source for c in caps] == ["bahn.de", "bahn.de"]
        assert all(c.raw_gz is not None and c.offer_count for c in caps)
        counts = [c.offer_count for c in caps]
    page = client.get(r.headers["location"]).text
    assert "2 captures from the HAR file." in page
    for n in counts:
        assert f"<td>{n}</td>" in page


def test_har_json_with_other_name_is_read_as_har(client, sessions, trip_id):
    r = _post(client, trip_id, source="", content=_har(), name="export.json")
    assert r.status_code == 303 and _count(sessions, trip_id) == 2


def test_har_with_no_supported_entry_stores_nothing(client, sessions, trip_id):
    content = json.dumps(har(entry("https://example.com/a.js", text="x"))).encode()
    r = _post(client, trip_id, source="", content=content, name="s.har")
    assert r.status_code == 400 and "no search entry of a supported source" in r.text
    assert _count(sessions, trip_id) == 0


def test_har_not_json_stores_nothing(client, sessions, trip_id):
    r = _post(client, trip_id, source="", content=b"not json", name="s.har")
    assert r.status_code == 400 and "cannot be read" in r.text
    assert _count(sessions, trip_id) == 0


def test_har_over_limit_stores_nothing(client, sessions, trip_id):
    r = _post(client, trip_id, source="", content=b" " * (MAX_HAR_BYTES + 1), name="s.har")
    assert r.status_code == 400 and "larger than" in r.text
    assert _count(sessions, trip_id) == 0
