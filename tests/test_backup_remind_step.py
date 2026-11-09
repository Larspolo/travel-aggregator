"""The service loop sends the due reminders at least every 15 minutes, and dumps only when due (#1647).

A fake clock steps through the loop, a fake dump writes a file, and the sends are doubles.
"""

from datetime import UTC, datetime, timedelta

from app import backup

NOW = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


class FakeDump:
    def __init__(self, backup_dir, fail_first=0):
        self.backup_dir = backup_dir
        self.fail_first = fail_first
        self.times = []

    def __call__(self, url, backup_dir, label):
        self.times.append(self.now)
        if len(self.times) <= self.fail_first:
            raise backup.BackupError("fake failure")
        path = backup_dir / f"{self.now:%Y%m%dT%H%M%SZ}-{label}.dump"
        path.write_bytes(b"dump")
        return path


def run_loop(monkeypatch, tmp_path, until, fail_first=0):
    fake = FakeDump(tmp_path, fail_first)
    reminds = []
    monkeypatch.setattr(backup, "dump", fake)
    monkeypatch.setattr(backup, "_check_step", lambda url, path, now: None)
    monkeypatch.setattr(backup, "_alert", lambda url, now, error: None)
    monkeypatch.setattr(backup, "_remind", lambda url, now: reminds.append(now))
    next_dump, now = NOW, NOW
    while now < until:
        fake.now = now
        next_dump, sleep_for = backup.loop_step("postgresql://fake", tmp_path, DAY, next_dump, now)
        now += timedelta(seconds=sleep_for)
    return fake, reminds


def test_a_day_with_one_good_dump_reminds_at_each_step(monkeypatch, tmp_path):
    fake, reminds = run_loop(monkeypatch, tmp_path, NOW + DAY)
    assert len(fake.times) == 1
    assert len(reminds) >= 96
    assert reminds[1] - reminds[0] == timedelta(minutes=15)


def test_a_failed_dump_is_retried_only_after_the_retry_delay(monkeypatch, tmp_path):
    fake, reminds = run_loop(monkeypatch, tmp_path, NOW + timedelta(hours=5), fail_first=1)
    assert fake.times[0] == NOW
    assert fake.times[1] - fake.times[0] == timedelta(seconds=backup.DAILY_RETRY_SECONDS)
    assert len(reminds) >= 5 * 4
