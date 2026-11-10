from fastapi.testclient import TestClient

from app.api.health import _built
from app.main import app


def test_health_returns_ok():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_names_the_commit_of_the_image(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILD_TIME_FILE", str(tmp_path / "missing"))
    _built.cache_clear()
    monkeypatch.setenv("GIT_SHA", "abc123")
    assert TestClient(app).get("/api/health").json() == {"status": "ok", "commit": "abc123", "built": "dev"}
    monkeypatch.delenv("GIT_SHA")
    assert TestClient(app).get("/api/health").json()["commit"] == "dev"
