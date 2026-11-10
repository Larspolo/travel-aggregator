from fastapi.testclient import TestClient

from app.api.health import _built
from app.main import app


def _health(monkeypatch, path) -> dict:
    monkeypatch.setenv("BUILD_TIME_FILE", str(path))
    _built.cache_clear()
    return TestClient(app).get("/api/health").json()


def test_health_gives_the_build_time_of_the_image(monkeypatch, tmp_path):
    build_time = tmp_path / "BUILD_TIME"
    build_time.write_text("2026-11-10T03:00:00Z\n", encoding="utf-8")
    body = _health(monkeypatch, build_time)
    assert body["built"] == "2026-11-10T03:00:00Z"
    assert body["status"] == "ok"
    assert "commit" in body


def test_health_says_dev_when_there_is_no_build_time_file(monkeypatch, tmp_path):
    assert _health(monkeypatch, tmp_path / "missing")["built"] == "dev"
