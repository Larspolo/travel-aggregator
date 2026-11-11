"""The "Report on GitHub" link of each failing source (#929)."""

import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.failure_report import MAX_URL, mask, report
from app.main import app
from app.models import Capture, Trip

PASSWORD = "pw"


def test_mask():
    assert mask("unknown station 'Berlin Hbf' at 12:30") == "unknown station '…' at N:N"
    assert mask('price "x"' + "a" * 300) == "price '…'" + "a" * 191


def _add(s, trip_id, minute, **kw):
    s.add(Capture(trip_id=trip_id, source="bahn.de", parser_version="0.0.1", raw_gz=b"x",
                  page_url="https://www.bahn.de/secret-url", search_context_json={"from": "Geheimstadt"},
                  captured_at=datetime(2026, 11, 3, 19, minute, tzinfo=UTC), **kw))


@pytest.fixture
def data(sessions):
    with sessions() as s:
        trip = Trip(title="Secret trip title")
        s.add(trip)
        s.flush()
        _add(s, trip.id, 1, unreadable="no key 'journeys' in 'Privatweg 12'")
        _add(s, trip.id, 2, offer_count=1, rejected_count=2,
             errors_json=[{"index": 0, "reason": "bad price \"99.50\""}, {"index": 1, "reason": "bad price \"12\""}])
        s.commit()
        return trip.id


def test_report_holds_counts_and_no_private_data(data, sessions):
    with sessions() as s:
        title, body = report(s, "bahn.de")
    text = title + body
    assert "bahn.de" in title
    assert "Failed captures after the last good capture: 2" in body
    assert "Unreadable payloads: 1" in body and "Rejected offers: 2" in body
    assert "2 × bad price '…'" in body and "1 × no key '…' in '…'" in body
    for secret in ("secret-url", "Secret trip", "Geheimstadt", "Privatweg", "journeys", "99", "2026"):
        assert secret not in text
    assert "trimmed payload" in body


def test_page_link_with_long_reasons(data, sessions, monkeypatch):
    with sessions() as s:
        for i in range(50):
            _add(s, data, 3, unreadable=("reason x" + "abcdefghij" * 19 + chr(65 + i % 26) + chr(97 + i // 26))[:200])
        s.commit()
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    login = c.get("/login").text
    c.post("/login", data={"password": PASSWORD, "csrf_token": re.search(r'csrf_token" value="([^"]+)"', login).group(1)})
    page = c.get("/captures?failed=1").text
    links = re.findall(r'<a class="report-link" href="([^"]+)" target="_blank" rel="noopener">Report on GitHub</a>', page)
    assert len(links) == 1
    url = links[0].replace("&amp;", "&")
    assert url.startswith("https://github.com/Larspolo/travel-aggregator/issues/new?")
    assert len(url) <= MAX_URL
    body = parse_qs(urlsplit(url).query)["body"][0]
    assert "Unreadable payloads: 51" in body and "trimmed payload" in body
