"""Each source with a parser gets the count and the reparse action of an older version (#2010, epic #1988)."""

import gzip
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.parsers import parser_classes

PASSWORD = "pw"
PAGE = "/captures"


def _csrf(c, path):
    groups = re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)
    return next(t for t in groups if t)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        tokens.create(s, "test")
        trip = Trip(title="Köln – München")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, sessions, trip_id


@pytest.mark.parametrize("source", sorted(parser_classes()))
def test_reparse_old_per_source(client, source):
    c, sessions, trip_id = client
    cls = parser_classes()[source]
    with sessions() as s:
        s.add(Capture(trip_id=trip_id, source=source, parser_version=cls.version,
                      captured_at=datetime(2026, 11, 3, 19, 40, tzinfo=UTC),
                      raw_gz=gzip.compress(b"{}"), offer_count=0, rejected_count=0,
                      parsed_with="0.0.0"))
        s.commit()
    page = c.get(PAGE).text
    assert "1 captures of an older version" in page
    pattern = (r'hx-vals=\'\{"source": "' + re.escape(source) + r'"\}\'[^>]*>\s*Reparse with version '
               + re.escape(cls.version) + r"</button>")
    assert re.search(pattern, page, re.S), source
