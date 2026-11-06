"""The readers of the branch `metrics` see a failed fetch (process review 2026-11-02): a parallel `git fetch` in the
same clone made the fetch of `metrics_log.load` fail, and `health.py` counted 0 run reports in 100 merged PRs (99 in
the 100 before) with no warning."""
import datetime
import subprocess

import health
import metrics_log

SINCE = datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc)


def done(code, out=""):
    return subprocess.CompletedProcess([], code, out, "")


def test_a_failed_fetch_is_tried_again(monkeypatch):
    calls = []

    def git(*args):
        calls.append(args[0])
        return done(1 if calls.count("fetch") == 1 and args[0] == "fetch" else 0)
    monkeypatch.setattr(metrics_log, "git", git)
    monkeypatch.setattr(metrics_log.time, "sleep", lambda s: None)
    monkeypatch.setattr(metrics_log, "read_runs", lambda ref, days: [])
    assert metrics_log.load(SINCE) == []
    assert calls.count("fetch") == 2


def test_two_failed_fetches_give_none(monkeypatch):
    monkeypatch.setattr(metrics_log, "git", lambda *a: done(1))
    monkeypatch.setattr(metrics_log.time, "sleep", lambda s: None)
    assert metrics_log.load(SINCE) is None


def test_health_warns_when_the_branch_cannot_be_read(monkeypatch, capsys):
    monkeypatch.setattr(metrics_log, "load", lambda since: None)
    monkeypatch.setattr(metrics_log, "api_comments", lambda since: [])
    assert health.status_comments(since=SINCE) == []
    assert "warning: git cannot read the branch metrics" in capsys.readouterr().err


def test_no_warning_when_the_branch_is_read(monkeypatch, capsys):
    monkeypatch.setattr(metrics_log, "load", lambda since: [])
    monkeypatch.setattr(metrics_log, "api_comments", lambda since: [])
    health.status_comments(since=SINCE)
    assert "warning" not in capsys.readouterr().err
