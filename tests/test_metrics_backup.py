"""The backup gauges of GET /metrics: age, size and check result of the newest dump (#1894)."""

import json
from datetime import UTC, datetime, timedelta

from app.backup import CHECK_KEY, STAMP_FORMAT
from app.models import Setting
from tests.test_metrics import _get, _new_token
from tests.test_upcoming_page import client  # noqa: F401  (fixture)


def _metric_lines(text: str, name: str) -> list[str]:
    return [x for x in text.splitlines() if x.startswith(name + " ")]


def _dump(folder, hours_ago: float, size: int = 1234) -> None:
    when = datetime.now(UTC) - timedelta(hours=hours_ago)
    (folder / f"{when.strftime(STAMP_FORMAT)}-daily.dump").write_bytes(b"x" * size)


def _store_check(sessions, value: dict) -> None:
    with sessions() as s:
        s.merge(Setting(key=CHECK_KEY, value=json.dumps(value)))
        s.commit()


def test_age_and_size_of_the_newest_backup(client, sessions, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    _dump(tmp_path, hours_ago=2, size=1234)
    _dump(tmp_path, hours_ago=5, size=999)
    text = _get(_new_token(client)).text
    (age,) = _metric_lines(text, "travel_backup_age_seconds")
    assert 7200 <= float(age.split()[1]) <= 7260
    assert _metric_lines(text, "travel_backup_size_bytes") == ["travel_backup_size_bytes 1234"]


def test_check_ok_with_tables(client, sessions, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    _dump(tmp_path, hours_ago=2)
    _store_check(sessions, {"file": "x", "tables": 12, "at": "2026-11-10T10:00:00+00:00"})
    text = _get(_new_token(client)).text
    assert _metric_lines(text, "travel_backup_check_ok") == ["travel_backup_check_ok 1"]


def test_check_failed_with_error(client, sessions, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    _dump(tmp_path, hours_ago=2)
    _store_check(sessions, {"file": "x", "error": "pg_restore failed", "at": "2026-11-10T10:00:00+00:00"})
    text = _get(_new_token(client)).text
    assert _metric_lines(text, "travel_backup_check_ok") == ["travel_backup_check_ok 0"]


def test_no_backup_directory_gives_no_backup_line(client, sessions, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "missing"))
    r = _get(_new_token(client))
    assert r.status_code == 200
    assert "travel_backup_" not in r.text
    assert "travel_trips 0" in r.text.splitlines()
