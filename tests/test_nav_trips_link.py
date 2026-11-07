"""The page header links to the trips list (#450)."""

import pytest
from fastapi.testclient import TestClient

from app.auth import require_login
from app.main import app


@pytest.fixture
def client(sessions):
    """A client with the owner login and a database."""
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)


def test_the_header_links_to_the_trips_list(client):
    page = client.get("/captures").text
    assert '<a href="/">Trips</a>' in page
