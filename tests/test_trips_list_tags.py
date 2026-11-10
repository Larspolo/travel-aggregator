"""The tags on the trips list and the filter `/?tag=` (#1951)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Trip
from app.share import hash_token

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    with Session(sessions.kw["bind"]) as s:
        s.add_all([
            Trip(title="Trip A", origin_text="Utrecht", destination_text="Zürich", tags_text="work, Zürich",
                 share_hash=hash_token("tok-a")),
            Trip(title="Trip B", origin_text="Utrecht", destination_text="Rome", tags_text="summer 2027"),
            Trip(title="Trip C", origin_text="Utrecht", destination_text="Oslo"),
            Trip(title="Trip D", origin_text="Utrecht", destination_text="Paris", tags_text="work",
                 status="archived"),
            Trip(title="Trip E", origin_text="Lyon", destination_text="Paris", tags_text="<script>x</script>"),
        ])
        s.commit()
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _titles(html: str) -> set[str]:
    return set(re.findall(r">(Trip [A-E])</a>", html))


def test_list_shows_tags(client):
    html = client.get("/").text
    assert 'href="/?tag=work"' in html and 'href="/?tag=summer%202027"' in html and ">Zürich</a>" in html


@pytest.mark.parametrize("tag", ["work", "Work"])
def test_filter(client, tag):
    html = client.get("/", params={"tag": tag}).text
    assert _titles(html) == {"Trip A"} and "Show all trips" in html and 'name="tag" value="' + tag + '"' in html


def test_filter_with_search_and_archive(client):
    assert _titles(client.get("/", params={"tag": "work", "q": "Zürich"}).text) == {"Trip A"}
    assert _titles(client.get("/", params={"tag": "work", "q": "Paris"}).text) == {"Trip D"}  # the archive part
    assert _titles(client.get("/", params={"tag": "work", "archived": 1}).text) == {"Trip D"}


def test_unknown_and_long_tag(client):
    html = client.get("/", params={"tag": "nothing"}).text
    assert "No trips with the tag" in html and "Show all trips" in html and not _titles(html)
    assert client.get("/", params={"tag": "x" * 21}).status_code == 422


def test_tag_is_text(client):
    html = client.get("/").text
    assert "<script>x" not in html and "&lt;script&gt;x&lt;/script&gt;" in html


def test_shared_page_has_no_tags(client):
    html = client.get("/s/tok-a").text
    assert "Trip A" in html and "work" not in html
