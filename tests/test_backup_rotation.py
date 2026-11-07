"""The rotation of the daily dumps: only the newest BACKUP_KEEP stay (app/backup.py)."""

from datetime import UTC, datetime, timedelta

import pytest

from app import backup

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def _name(hours_ago: int, label: str) -> str:
    return f"{(NOW - timedelta(hours=hours_ago)):%Y%m%dT%H%M%SZ}-{label}.dump"


@pytest.fixture
def dumps(tmp_path):
    out = tmp_path / "bk"
    out.mkdir()
    for h in range(16):
        (out / _name(24 * h, "daily")).write_bytes(b"d")
    (out / _name(1, "manual")).write_bytes(b"m")
    (out / _name(2, "0042")).write_bytes(b"p")   # a pre-migration dump: named by its revision
    return out


def test_rotation_keeps_the_newest_daily_dumps_and_the_other_two(dumps, monkeypatch):
    monkeypatch.setenv("BACKUP_KEEP", "14")
    deleted = backup.rotate_daily(dumps, backup.keep_count())
    assert len(deleted) == 2
    kept = sorted(p.name for p in dumps.glob("*-daily.dump"))
    assert len(kept) == 14
    assert kept == sorted(_name(24 * h, "daily") for h in range(14))
    assert (dumps / _name(1, "manual")).exists()
    assert (dumps / _name(2, "0042")).exists()


@pytest.mark.parametrize("value", ["0", "-3", "many", "1.5"])
def test_bad_keep_gives_the_default_and_says_so(value, monkeypatch, capsys):
    monkeypatch.setenv("BACKUP_KEEP", value)
    assert backup.keep_count() == 14
    assert "keep 14" in capsys.readouterr().err


def test_unset_keep_is_the_default_without_a_line(monkeypatch, capsys):
    monkeypatch.delenv("BACKUP_KEEP", raising=False)
    assert backup.keep_count() == 14
    assert capsys.readouterr().err == ""


def test_keep_of_one_leaves_only_the_newest(dumps, monkeypatch):
    monkeypatch.setenv("BACKUP_KEEP", "1")
    backup.rotate_daily(dumps, backup.keep_count())
    assert [p.name for p in dumps.glob("*-daily.dump")] == [_name(0, "daily")]
