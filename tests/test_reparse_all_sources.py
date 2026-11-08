"""Reparse all failed captures of each source of app/parsers (#498, criterion of epic #488)."""

import importlib
import json
import pkgutil
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import ingest, parsers as parsers_pkg, tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Itinerary, Trip
from app.parsers import get_parser

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "pw"
PAGE = "/captures?failed=1"


class RaisingParser:
    version = "0.0.1"

    def parse(self, raw):
        raise ValueError("format changed")


def _parser_sources() -> list[str]:
    """The `source` of each parser class in the modules of app/parsers (found, not listed)."""
    sources = []
    for module_info in pkgutil.iter_modules(parsers_pkg.__path__):
        module = importlib.import_module(f"{parsers_pkg.__name__}.{module_info.name}")
        for obj in vars(module).values():
            if isinstance(obj, type) and hasattr(obj, "source") and hasattr(obj, "parse"):
                sources.append(obj.source)
    return sorted(set(sources))


SOURCES = _parser_sources()


def test_every_parser_source_has_a_parser():
    assert len(SOURCES) == 8, SOURCES
    for source in SOURCES:
        assert get_parser(source) is not None, source


def _csrf(c, path):
    groups = re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)
    return next(t for t in groups if t)


def _first_fixture(source: str) -> dict:
    """The first fixture that the parser reads with no rejected connection: "now parse" counts only such a capture
    (a real capture can have a connection with no price, #485)."""
    for path in sorted((FIXTURES / source).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            if not get_parser(source).parse(raw).errors:
                return raw
        except ValueError:
            continue
    raise AssertionError(f"no fixture of {source} parses with no error")


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Reparse all sources")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, trip_id, {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("source", SOURCES)
def test_reparse_all_failed_captures_of_source(client, sessions, monkeypatch, source):
    c, trip_id, auth = client
    raw = _first_fixture(source)
    with monkeypatch.context() as m:
        m.setattr(ingest, "get_parser", lambda s: RaisingParser())
        for minute in (1, 2):
            r = c.post("/api/ingest", headers=auth, json={
                "trip_id": trip_id, "source": source, "parser_version": "0.0.1",
                "captured_at": f"2026-11-03T19:4{minute}:00Z", "raw": raw})
            assert r.status_code < 300, r.text
    assert f"failed captures of {source}" in c.get(PAGE).text

    # The real parser is the fix: remove the patch and reparse all failed captures of the source.
    r = c.post("/captures/reparse-failed", data={"source": source}, headers={"X-CSRF-Token": _csrf(c, PAGE)})
    assert r.status_code == 200, r.text
    assert f"Reparsed 2 captures of {source}" in r.text
    assert "2 now parse, 0 still fail" in r.text
    assert f"failed captures of {source}" not in c.get(PAGE).text
    with sessions() as s:
        assert s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).first() is not None
        failed = s.scalars(select(Capture).where(Capture.source == source, Capture.unreadable.is_not(None))).all()
        assert failed == []
