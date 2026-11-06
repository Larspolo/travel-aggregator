"""`claim.py 0 --stuck` leaves out a ticket whose PR only waits (`pacer.ci_wait`), and a green PR that Automerge never
merges waits for the owner, not for a takeover (#5331)."""
import claim
import ship_pr

GREEN = [{"name": ship_pr.QUICK, "status": "completed", "conclusion": "success"}]
RED = [{"name": ship_pr.QUICK, "status": "completed", "conclusion": "failure"}]


def pr(ref, sha, labels=()):
    return {"number": 5300, "body": "Closes #5297", "head": {"ref": ref, "sha": sha},
            "labels": [{"name": x} for x in labels]}


def lines(p):
    return claim.stuck_lines([(5297, "Beat #5297, 65 min ago")], [p], {"g": GREEN, "r": RED}.get)


def test_green_agent_pr_gives_no_line():
    assert lines(pr("claude/x", "g")) == []


def test_green_owner_pr_waits_for_the_owner():
    assert lines(pr("dat-compare-fix", "g")) == [
        "#5297 PR #5300 waits for the owner (no agent branch, no label automerge)"]


def test_green_owner_pr_with_label_automerge_gives_no_line():
    assert lines(pr("dat-compare-fix", "g", ["automerge"])) == []


def test_red_pr_gives_the_takeover_line():
    assert lines(pr("dat-compare-fix", "r")) == ["#5297 PR #5300: Beat #5297, 65 min ago"]
    assert lines(pr("claude/x", "r")) == ["#5297 PR #5300: Beat #5297, 65 min ago"]
