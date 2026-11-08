"""The web app manifest lets a phone open the app as an app, and each page links it (#797)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_manifest_answers_with_no_login(client):
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")


def test_manifest_has_the_keys_of_the_app(client):
    data = client.get("/manifest.webmanifest").json()
    assert data["name"] == "travel-aggregator"
    assert data["short_name"] == "Travel"
    assert data["start_url"] == "/"
    assert data["scope"] == "/"
    assert data["display"] == "standalone"
    assert data["background_color"] == "#f5f5f7"
    assert data["theme_color"] == "#5145d6"


def test_each_icon_of_the_manifest_answers_200(client):
    icons = client.get("/manifest.webmanifest").json()["icons"]
    assert {icon["src"] for icon in icons} == {
        "/static/icon-192.png", "/static/icon-512.png", "/static/icon-maskable-512.png"}
    assert [i for i in icons if i.get("purpose") == "maskable"][0]["src"] == "/static/icon-maskable-512.png"
    for icon in icons:
        assert client.get(icon["src"]).status_code == 200


def test_login_page_links_the_manifest_and_theme_colour(client):
    html = client.get("/login").text
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert '<meta name="theme-color" content="#5145d6">' in html
