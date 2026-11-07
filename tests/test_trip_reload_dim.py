"""The trip table is dimmed while the sliders reload it (#665): the weights form names the table as its indicator,
and the CSS dims the table card while htmx sets its request class."""

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_trip_page import ingest, offer

CSS = "app/web/static/app.css"


@pytest.fixture
def client(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    test_client = TestClient(app)
    ingest(test_client, {"Authorization": f"Bearer {token}"}, trip_id, [offer(49)])
    app.dependency_overrides[require_login] = lambda: None
    yield test_client, trip_id
    app.dependency_overrides.pop(require_login, None)


def test_weights_form_names_the_table_as_indicator(client):
    test_client, trip_id = client
    response = test_client.get(f"/trips/{trip_id}")
    assert response.status_code == 200
    html = response.text
    form_tag = html[html.index('<form class="weights"'):].split(">", 1)[0]
    assert 'hx-target="#table"' in form_tag
    assert 'hx-indicator="#table"' in form_tag


def test_table_card_dims_while_request_runs():
    css = open(CSS, encoding="utf-8").read()
    assert ".table-card.htmx-request { opacity: .55;" in css
    assert "transition: opacity 120ms" in css
