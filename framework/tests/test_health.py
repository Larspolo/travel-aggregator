"""framework/tools/health.py: the numbers for the improve skill, with fixture data (no network)."""
import datetime

import health

SINCE = datetime.datetime(2026, 10, 25, 12, tzinfo=datetime.timezone.utc)


def run(name, start, end, conclusion="success", status="completed"):
    return dict(name=name, run_started_at=start, updated_at=end, conclusion=conclusion, status=status)


def test_ci_runs():
    runs = [run("CI", "2026-10-25T13:00:00Z", "2026-10-25T13:03:00Z"),
            run("CI", "2026-10-25T14:00:00Z", "2026-10-25T14:05:00Z", "failure"),
            run("CI", "2026-10-25T15:00:00Z", "2026-10-25T15:02:00Z"),
            run("CI", "2026-10-25T11:00:00Z", "2026-10-25T11:30:00Z"),            # before the period
            run("CI", "2026-10-25T16:00:00Z", "2026-10-25T16:01:00Z", None, "in_progress"),
            run("Dashboard", "2026-10-25T13:00:00Z", "2026-10-25T13:00:30Z")]
    assert health.ci_runs(runs, SINCE) == {"CI": (3, 3.0, 5.0, 1), "Dashboard": (1, 0.5, 0.5, 0)}


def test_slow_steps():
    def step(name, a, b):
        return dict(name=name, started_at=f"2026-10-25T13:{a:02d}:00Z", completed_at=f"2026-10-25T13:{b:02d}:00Z")
    jobs = [dict(name="test", steps=[step("Lint", 0, 1), step("Slow", 1, 4), step("Fast", 4, 6)]),
            dict(name="test", steps=[step("Lint", 0, 1), step("Slow", 1, 6), step("Fast", 6, 8),
                                     dict(name="Skipped", started_at=None, completed_at=None)])]
    assert health.slow_steps(jobs, 2) == [(4.0, "test / Slow"), (2.0, "test / Fast")]


def test_setup_minutes():
    comments = [{"body": "Run X.\n\nMetrics: ticket #5 · size:S · merged · 9 min · setup 2 min · CI runs 1 · CI 3 min"},
                {"body": "Metrics: ticket #6 · size:M · merged · 12 min · setup 0.5 min · CI runs 2"},
                {"body": "The setup 9 min line is not a Metrics line."}]
    assert health.setup_minutes(comments) == [2.0, 0.5]


def test_events():
    comments = [{"body": "Taken over by `claude/a`: stalled."}, {"body": "Released: claimed twice."},
                {"body": "Released: usage limit."},
                {"body": "CI is green, but the merge failed (Pull Request is not mergeable). Merge ..."},
                {"body": "Started by `claude/b`."}, {"body": None},
                {"body": "Merged `main` into the branch: git solved the conflict alone (`merge=union`). CI runs again."},
                {"body": "Run of `claude/c`: PR #9 had a merge conflict, merged main."}]       # a report: no count
    assert health.events(comments) == {"takeovers": 1, "conflicts": 1, "solved": 1}   # "Released" is no count (#5649)


def test_claim_to_merge():
    url = "https://api.github.com/repos/Larspolo/travel-aggregator/issues/"
    comments = [{"body": "Started by `a`.", "issue_url": url + "5", "created_at": "2026-10-25T13:00:00Z"},
                {"body": "Started by `b`.", "issue_url": url + "5", "created_at": "2026-10-25T13:10:00Z"},
                {"body": "Started by `c`.", "issue_url": url + "5", "created_at": "2026-10-25T15:00:00Z"},  # after
                {"body": "Started by `d`.", "issue_url": url + "6", "created_at": "2026-10-25T10:00:00Z"}]
    prs = [{"body": "Closes #5", "merged_at": "2026-10-25T13:30:00Z"},
           {"body": "Closes #6", "merged_at": "2026-10-25T12:30:00Z"},
           {"body": "Closes #6", "merged_at": "2026-10-25T11:00:00Z"},              # before the period
           {"body": "Closes #7", "merged_at": None}]
    assert health.claim_to_merge(prs, comments, SINCE) == [20.0, 150.0]


def test_bad_files():
    files = [("travel-aggregator.py", 200_000), ("docs/img/a.png", 50_000), ("out/a.png", 10), ("logs/latest.log", 10),
             ("samples/big.bin", 5 << 20), ("r.0.0.mca", 10)]
    assert health.bad_files(files) == [("out/a.png", 10), ("logs/latest.log", 10),
                                       ("samples/big.bin", 5 << 20), ("r.0.0.mca", 10)]


def test_report():
    text = health.report(SINCE, [run("CI", "2026-10-25T13:00:00Z", "2026-10-25T13:03:00Z")], [], [], [], [], [])
    assert "  CI: 1, 3.0, 3.0, 0" in text and "Setup (median min of 0 Metrics lines): -" in text
