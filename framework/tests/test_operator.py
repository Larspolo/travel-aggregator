"""framework/tools/operator_check.py: the checks of framework/docs/OPERATOR.md that need no session tools (#981)."""
import datetime

import operator_check as oc

NOW = datetime.datetime(2026, 10, 26, 16, 0, tzinfo=datetime.timezone.utc)


def test_wanted_labels_skip_comments_and_blank_lines():
    text = "# name|color|description\nP0|b60205|Do next\n\nmuted|ededed|Later  \n"
    assert oc.wanted_labels(text) == ["P0", "muted"]


def test_missing_labels():
    assert oc.missing_labels(["P0", "muted", "process"], [{"name": "P0"}, {"name": "bug"}]) == ["muted", "process"]


def test_old_prs_are_agent_prs_older_than_the_limit():
    def pr(n, ref, minutes):
        return {"number": n, "head": {"ref": ref}, "created_at": f"{NOW - datetime.timedelta(minutes=minutes):%FT%TZ}"}
    prs = [pr(1, "claude/a", 45), pr(2, "agent/9-x", 10), pr(3, "owner-branch", 90), pr(4, "agent/5-y", 31)]
    assert [p["number"] for p in oc.old_prs(prs, NOW)] == [1, 4]


def test_ci_check_red_only_on_failure():
    run = {"conclusion": "failure", "status": "completed", "head_sha": "abcdef123", "created_at": "2026-10-26T15:00:00Z"}
    assert oc.ci_check("CI", [run]) == (False, "CI: failure (abcdef1, 2026-10-26T15:00:00Z)")
    assert oc.ci_check("CI", [dict(run, conclusion="cancelled")])[0]
    assert oc.ci_check("CI", [dict(run, conclusion=None, status="in_progress")]) == (
        True, "CI: in_progress (abcdef1, 2026-10-26T15:00:00Z)")
    assert oc.ci_check("CI", []) == (True, "CI: no run")


def test_report_exit_code():
    lines, code = oc.report([("quota", True, "5%"), ("labels", False, "muted")])
    assert lines == ["OK      quota: 5%", "PROBLEM labels: muted"] and code == 1
    assert oc.report([("quota", True, "5%")])[1] == 0
