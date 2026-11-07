"""GET /trips/{id} (#119): the page links to the manual offer form of the trip."""

import pytest
from fastapi.testclient import TestClient

from app.auth import require_login
from app.main import app
from app.models import Trip


@pytest.fixture
def trip(sessions):
    """A client with the owner login and an empty trip."""
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), trip_id
    app.dependency_overrides.pop(require_login, None)


def test_the_trip_page_links_to_the_manual_offer_form(trip):
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    assert f'href="/trips/{trip_id}/offers/new"' in page
    assert "Add an offer by hand" in page
