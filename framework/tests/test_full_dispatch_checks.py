"""A `full` CI dispatch on the head of a PR does not gate the PR (#5462): its red slow or server jobs kept #5410 out
of each Automerge sweep for 5 hours and gave its ticket #5400 2 takeovers. The PR's own CI decides, in the sweep of
`automerge.yml` (GREEN) and in `pacer.ci_wait` (the stuck tickets)."""
import json
import os
import re
import subprocess

import pacer
import pytest

WORKFLOW = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "automerge.yml")


def check(name, suite, conclusion="success", status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion, "check_suite": {"id": suite}}


OWN = [check("quick", 1), check("slow", 1, "skipped"), check("mc", 1, "skipped")]
FULL = [check("quick", 2, "failure"), check("slow", 2, "failure"), check("mc (1)", 2, "failure"), check("data", 2)]


def green(checks):
    """The result of the GREEN filter of the sweep, as jq runs it."""
    flt = re.search(r"^\s*GREEN='(.*?)'$", open(WORKFLOW).read(), re.M | re.S).group(1)
    return subprocess.run(["jq", "-e", flt], input=json.dumps(checks), capture_output=True, text=True).returncode == 0


@pytest.mark.parametrize("checks, want", [
    (OWN, True),                                                    # the PR's own quick CI is green
    (OWN + FULL, True),                                             # a red full dispatch on the same head
    (OWN + [check("slow", 2, None, "in_progress")], True),          # a full dispatch still runs
    (FULL, False),                                                  # only the full dispatch: no own quick check
    ([check("quick", 1, "failure")] + FULL, False),                 # the own quick CI is red
    (OWN + [check("site", 3, "failure")], False),                   # another PR check failed
    ([check("quick", 4)], True),                                    # an Unconflict dispatch (no slow job) is own CI
])
def test_the_sweep_and_ci_wait_judge_the_own_ci(checks, want):
    assert green(checks) is want
    assert (pacer.ci_wait({"labels": []}, checks) == "green") is want


def test_pr_checks_drops_only_the_full_suites():
    assert pacer.pr_checks(OWN + FULL) == OWN
    assert pacer.pr_checks([check("quick", 4)]) == [check("quick", 4)]
