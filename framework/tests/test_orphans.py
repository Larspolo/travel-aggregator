"""Open tickets and agent PRs that no run, workflow or owner list takes up again show in `cycle_start.py` (#4553)."""
import datetime

import cycle_start as start
import dashboard

NOW = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=datetime.timezone.utc)


def issue(n, labels=(), body="", title=None):
    return {"number": n, "title": title or f"Ticket {n}", "labels": [{"name": x} for x in labels], "body": body}


def test_tickets_that_wait_for_nothing_are_orphans():
    issues = [issue(1, ["P3", "blocked"], "Depends on: #2"), issue(2, ["P3"]),               # waits for open #2
              issue(3, ["P3", "blocked"], "Depends on: #99"),                                # #99 is closed
              issue(4, ["P3", "blocked"]),                                                   # no line at all
              issue(5, ["P3", "blocked", "needs-human"]),                                    # the owner sees it
              issue(6, ["P3"], title="Decide: the colour"), issue(7, ["P3", "needs-human"], title="Decide: the size"),
              issue(8, ["P3"], "Depends on: #9"), issue(9, ["P3"], "Depends on: #8"),        # a cycle
              issue(10, ["P3"], "Start after: 5 PRs after #50"),                             # #50 closed, not merged
              issue(11, ["P3"], "Start after: 5 PRs after #51"),                             # #51 merged
              issue(12, ["P3"], "Start after: 5 PRs after #52"), {"number": 52, "pull_request": {}},   # #52 open PR
              issue(13, ["P3", "blocked", "muted"]), issue(14, ["P3", "in-progress", "blocked"])]
    got = dict(dashboard.orphans(issues, after={51: 2}.get))
    assert sorted(got) == [3, 4, 6, 8, 9, 10]
    assert "blocked" in got[3] and "needs-human" in got[6] and "cycle" in got[8] and "#50" in got[10]


def test_a_start_after_line_on_no_pr_is_an_orphan():
    def after(m):
        raise ValueError("404")
    assert [n for n, _ in dashboard.orphans([issue(1, ["P3"], "Start after: 1 PR after #40")], after=after)] == [1]


def pr(labels=(), minutes=60):
    t = (NOW - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"number": 70, "head": {"ref": "claude/x-1"}, "body": "Closes #7", "created_at": t, "updated_at": t,
            "labels": [{"name": n} for n in labels]}


ISSUES = {7: issue(7, ["in-progress"]), 8: issue(8, ["needs-human"])}
GREEN = [("quick", "completed", "success")]


def test_a_hold_pr_that_no_run_holds_is_work():
    assert "remove `hold`" in start.pr_work(pr(["hold"]), ISSUES, GREEN, (45, "Beat #7 by claude/x-1"), NOW)
    assert start.pr_work(pr(["hold"]), ISSUES, GREEN, (5, "Beat #7 by claude/x-1"), NOW) is None     # a live run
    assert start.pr_work(pr(["hold"], minutes=10), ISSUES, GREEN, None, NOW) is None                # a new change
    held = dict(pr(["hold"]), body="Closes #8")
    assert start.pr_work(held, ISSUES, GREEN, None, NOW) is None                                    # owner waits


def test_a_pr_with_no_ci_run_is_work():
    assert "start CI" in start.pr_work(pr(), ISSUES, [], None, NOW)
    assert start.pr_work(pr(minutes=10), ISSUES, [], None, NOW) is None                             # CI can start
    assert "take it over" in start.pr_work(pr(["conflict"]), ISSUES, [], None, NOW)                 # dirty: no CI
