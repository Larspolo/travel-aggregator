"""The report and the red CI of the old run in `health.takeovers` (#4777): a report names its branch with no backticks
("Run: ... · branch b/a · ..."), and a run that the pacer started has the claim name `pacer-r...` in its "Started by"
comment, not its branch. 28 of 33 "no report" takeovers of 2026-10-30 had a report."""
import health


def c(n, t, body):
    return {"issue_url": f"https://api.github.com/repos/o/r/issues/{n}", "created_at": f"2026-10-30T{t}:00Z",
            "body": body}


def report(t, branch, ticket):
    return c(1, t, f"Did it.\nMetrics: ticket #{ticket} · size:S · pr #2{ticket % 10}\n"
                   f"Run: 1-2 · branch {branch} · start 2026-10-30T00:00:00Z · wall 5 min")


def ci(branch, t, conclusion):
    return {"name": "CI", "head_branch": branch, "created_at": f"2026-10-30T{t}:00Z", "status": "completed",
            "conclusion": conclusion}


PRS = [{"number": 21, "body": "Closes #11", "head": {"ref": "b/c"}, "created_at": "2026-10-30T03:10:00Z"},
       {"number": 22, "body": "Closes #12", "head": {"ref": "b/d"}, "created_at": "2026-10-30T05:10:00Z"}]
COMMENTS = [
    c(10, "01:00", "Started by `b/a`."),
    c(10, "02:00", "Taken over by `b/x`: stalled."),                       # its report names the branch
    c(11, "03:00", "Started by `pacer-r0123456789`. Session: https://claude.ai/code/s"),
    c(11, "04:00", "Taken over by `b/y`. Stuck: its run stopped."),        # its report names the PR branch
    c(12, "05:00", "Started by `pacer-r9876543210`."),
    c(12, "06:00", "Taken over by `b/z`. Stuck: its run stopped."),        # reported, then the CI of its PR failed
    c(13, "07:00", "Started by `b/e`."),
    c(13, "08:00", "Taken over by `b/w`: stuck."),                         # no report
]
STATUS = [report("01:30", "b/a", 10), report("03:20", "b/c", 11), report("05:20", "b/d", 12),
          report("07:30", "b/q", 99)]
RUNS = [ci("b/d", "05:15", "success"), ci("b/d", "05:40", "failure"), ci("b/d", "06:30", "success")]


def test_a_report_with_the_branch_without_backticks_or_of_the_pr_branch_counts():
    rows = health.takeovers(COMMENTS, STATUS, PRS)
    assert [(i, m, cause) for _, i, _, m, cause in rows] == [
        (10, 30, "after the report"), (11, 40, "after the report"), (12, 40, "after the report"), (13, None, "no report")]


def test_the_last_ci_run_of_the_pr_before_the_takeover_failed():
    rows = health.takeovers(COMMENTS, STATUS, PRS, runs=RUNS)
    assert [cause for *_, cause in rows] == ["after the report", "after the report", "red CI", "no report"]
    assert health.takeover_lines(rows)[-1] == "Takeover causes: red CI 1, no report 1, after the report 2"
