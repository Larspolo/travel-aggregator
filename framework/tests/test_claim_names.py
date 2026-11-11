"""A run keeps its claim when it changes its branch (#1800): `claim.names()` has each name that the run claimed or
adopted with. #1560: a run read its own beat as a takeover after a branch change, and its report kept the claim, so a
takeover came 41 minutes later. #1665: a run that released its pacer claim by mistake could not claim it again."""
import subprocess
import sys

import claim
import report
from test_claim import TOOL, clones, run, tool  # noqa: F401  (clones is a fixture)


def test_a_beat_after_a_branch_change_is_still_the_own_beat(clones):  # noqa: F811
    a, b, _ = clones
    assert tool(a, "7").returncode == 0
    run("git", "checkout", "-q", "-b", "agent/7-other", cwd=a)
    r = tool(a, "7", "--beat")
    assert r.returncode == 0, r.stdout + r.stderr
    assert tool(b, "7", "--beat").returncode != 0                     # another run is still another run


def test_an_adopted_name_is_a_name_of_the_run(clones):  # noqa: F811
    a, _, _ = clones
    sha = run("git", "commit-tree", claim.EMPTY_TREE, "-m", "Claim #9 by pacer-rabc (x) lane haiku", cwd=a).strip()
    run("git", "push", "-q", "origin", f"{sha}:refs/heads/claim/9", cwd=a)
    assert tool(a, "9", "--adopt", "pacer-rabc").returncode == 0
    got = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {repr(TOOL.rsplit('/', 1)[0])}); "
                          "import claim; print(sorted(claim.names()))"], cwd=a, capture_output=True, text=True).stdout
    assert "pacer-rabc" in got and "run-0" in got


def test_started_by_of_an_own_name_is_not_another_run():
    comments = [{"body": "Started by `pacer-rabc`. Session: x", "created_at": "2026-11-09T21:39:44Z"}]
    now = claim.datetime.datetime(2026, 11, 9, 21, 45, tzinfo=claim.datetime.timezone.utc).timestamp()
    assert claim.started_by_other(comments, {"claude/x", "pacer-rabc"}, now) is None
    assert claim.started_by_other(comments, "claude/x", now) == "pacer-rabc"


def test_the_report_hands_off_a_claim_of_an_older_branch_of_the_run():
    claims = {1: "Beat #1 by claude/x lane haiku", 2: "Beat #2 by claude/other"}
    assert report.handoffs([1, 2], claims, [], {"agent/1-y", "claude/x"}) == [1]
