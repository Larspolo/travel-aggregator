"""The takeovers in framework/tools/health.py: the old run and the cause of each takeover (#1703)."""
import datetime

import health


def c(n, t, body):
    return {"issue_url": f"https://api.github.com/repos/o/r/issues/{n}", "created_at": f"2026-10-27T{t}:00Z",
            "body": body}


def usage(t, pct):
    return f"Usage: 2026-10-27T{t}:00Z · usage {pct}% · resets 2026-10-27T20:50:00Z · runs 5"


PRS = [{"number": 20, "title": "x", "body": "Closes #10", "head": {"ref": "b/a"}},
       {"number": 21, "title": "y", "body": "Closes #11", "head": {"ref": "b/c"}}]
COMMENTS = [
    c(10, "01:00", "Started by `b/a`."),
    c(20, "02:00", "CI is green, but the merge failed (Pull Request has merge conflicts)."),
    c(20, "02:40", "Taken over by `b/x`: stalled."),                       # conflict, the PR names the ticket
    c(11, "03:00", "Started by `b/c`."),
    c(11, "04:00", "Taken over by `b/y`: stalled."),                       # a report with -m mc
    c(12, "05:00", "Started by `b/d`."),
    c(12, "06:00", "Taken over by `b/z`: stalled."),                       # no report
    c(13, "07:00", "Started by `b/e`."),
    c(13, "09:00", "Taken over by `b/w`: stalled."),                       # usage at 100 %
    c(14, "10:00", "Started by `b/f`."),
    c(14, "11:00", "Taken over by `b/v`: stalled."),                       # reported, then gone
]
STATUS = [c(1, "02:00", "Run `b/a`: PR #20."), c(1, "03:30", "Run `b/c`: the -m mc tests run."),
          c(1, "05:30", "Run `b/q`: other."), c(1, "08:00", "Run `b/e`.\n" + usage("08:00", "100.0")),
          c(1, "10:30", "Run `b/f`.\n" + usage("10:30", "40.0"))]


def test_each_takeover_has_its_old_run_and_cause():
    rows = health.takeovers(COMMENTS, STATUS, PRS)
    assert [(i, old, m, cause) for _, i, old, m, cause in rows] == [
        (20, "b/a", 40, "merge conflict"), (11, "b/c", 30, "long mc test"), (12, "b/d", None, "no report"),
        (13, "b/e", 60, "quota"), (14, "b/f", 30, "after the report")]


def test_the_period_and_the_count_of_the_causes():
    since = datetime.datetime(2026, 10, 27, 5, 0, tzinfo=datetime.timezone.utc)
    lines = health.takeover_lines(health.takeovers(COMMENTS, STATUS, PRS, since))
    assert len(lines) == 4 and lines[0].startswith("  2026-10-27 06:00 #12 b/d: last report - before")
    assert lines[-1] == "Takeover causes: quota 1, no report 1, after the report 1"
    text = health.report(since, [], [], STATUS, COMMENTS, PRS, [])
    assert "Takeover causes: quota 1, no report 1, after the report 1" in text.splitlines()
