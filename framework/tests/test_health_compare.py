"""framework/tools/health.py --compare: the last period next to the period before (#1697), and --until without a zone."""
import datetime

import health

UNTIL = datetime.datetime(2026, 10, 27, 1, 0, tzinfo=datetime.timezone.utc)


def fake(monkeypatch, seen):
    def fetch(since, until):
        seen.append((since, until))
        return [], [], [], [], [], [], []
    monkeypatch.setattr(health, "fetch", fetch)
    monkeypatch.setattr(health, "git_files", lambda: [])
    monkeypatch.setattr(health, "owner_and_waits", lambda since, until=None: ([], []))
    monkeypatch.setattr(health, "claim_refs", lambda: None)
    monkeypatch.setattr("feedback.fetch", lambda: [])
    # No network: the open PRs and the pacer runs change between two calls (#5619)
    monkeypatch.setattr(health, "api", lambda path: {"workflow_runs": [], "jobs": []} if "runs" in path else [])


def test_until_without_a_zone_is_utc(monkeypatch, capsys):
    seen = []
    fake(monkeypatch, seen)
    assert health.main(["--hours", "6", "--until", "2026-10-27T01:00"]) == 0
    plain = capsys.readouterr().out
    assert health.main(["--hours", "6", "--until", "2026-10-27T01:00:00Z"]) == 0
    assert capsys.readouterr().out == plain
    assert seen == [(UNTIL - datetime.timedelta(hours=6), UNTIL)] * 2


def test_compare_prints_the_two_periods(monkeypatch, capsys):
    seen = []
    fake(monkeypatch, seen)
    assert health.main(["--hours", "6", "--compare", "--until", "2026-10-27T01:00"]) == 0
    out = capsys.readouterr().out
    h6 = datetime.timedelta(hours=6)
    assert seen == [(UNTIL - h6, UNTIL), (UNTIL - 2 * h6, UNTIL - h6)]
    assert out.startswith("Health since 2026-10-26 19:00 UTC until 2026-10-27 01:00 UTC\n"
                          "  before: Health since 2026-10-26 13:00 UTC until 2026-10-26 19:00 UTC\n")


def test_compare_pairs_the_lines_by_name():
    last = "Head\nA: 1\nCI runs:\n  quick: 3\nB: 2\nTakeovers 2, conflicts 5"
    before = "Head\nA: 1\nCI runs:\n  quick: 2\n  slow: 1\nB: 5\nTakeovers 7, conflicts 15"
    assert health.compare(last, before).splitlines() == [
        "Head", "A: 1", "CI runs:", "  quick: 3", "  before: quick: 2", "  before: slow: 1", "B: 2", "  before: B: 5",
        "Takeovers 2, conflicts 5", "  before: Takeovers 7, conflicts 15"]
