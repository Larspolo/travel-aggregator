"""A takeover finds the report of the old run in a run record of the branch `metrics` (its `branch` field)."""
import health
from test_health_takeovers import c


def test_a_run_record_with_the_branch_of_the_old_run_is_its_report():
    comments = [c(12, "05:00", "Started by `claude/s-abc-2`."), c(12, "06:00", "Taken over by `b/z`: stalled.")]
    record = {**c(1, "05:30", "Metrics: ticket #12\\nRun: x · branch claude/s-abc-3 · lane opus"),
              "branch": "claude/s-abc-3"}
    other = {**c(1, "05:40", "Run: y · branch claude/s-abd · lane opus"), "branch": "claude/s-abd"}
    rows = health.takeovers(comments, [record, other])
    assert [(old, m, cause) for _, _, old, m, cause in rows] == [("claude/s-abc-2", 30, "after the report")]


def test_no_record_of_the_old_run_is_no_report():
    comments = [c(12, "05:00", "Started by `claude/s-abc`."), c(12, "06:00", "Taken over by `b/z`: stalled.")]
    other = {**c(1, "05:30", "Run: y"), "branch": "claude/s-abcd"}
    assert health.takeovers(comments, [other])[0][4] == "no report"
