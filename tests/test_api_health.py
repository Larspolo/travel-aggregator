from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_names_the_commit_of_the_image(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123")
    assert TestClient(app).get("/api/health").json() == {"status": "ok", "commit": "abc123"}
    monkeypatch.delenv("GIT_SHA")
    assert TestClient(app).get("/api/health").json()["commit"] == "dev"
