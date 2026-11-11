"""The pages have a favicon (#531): an inline SVG, so the browser sends no request for /favicon.ico."""

import pytest
from fastapi.testclient import TestClient

from app.auth import require_login
from app.main import app


@pytest.mark.parametrize("path", ["/login", "/"])
def test_page_has_favicon(sessions, path):
    app.dependency_overrides[require_login] = lambda: None
    try:
        html = TestClient(app).get(path).text
    finally:
        app.dependency_overrides.pop(require_login, None)
    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' in html
