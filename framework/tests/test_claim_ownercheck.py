"""framework/tools/claim.py --ownercheck: one run makes the owner check ticket of an epic line (#1797: two runs made two
checks of epic #1780 in 2 minutes, and the owner got two requests)."""
import os
import subprocess
import sys

import claim
import cycle_start as start
from test_claim import clones, tool  # noqa: F401 (fixture)

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "claim.py")


def test_one_run_makes_the_owner_check(clones):  # noqa: F811
    """Three runs at the same time: one gets the lock. Another line of the same epic gives a new lock."""
    procs = [subprocess.Popen([sys.executable, TOOL, "1780", "--ownercheck", "--state", "1781"], cwd=d,
                              stdout=subprocess.PIPE, text=True) for d in clones]
    assert sorted(p.wait() for p in procs) == [0, 1, 1]
    again = tool(clones[1], "1780", "--ownercheck", "--state", "1781")
    assert again.returncode == 1 and "another run makes the ticket" in again.stdout
    assert tool(clones[2], "1780", "--ownercheck", "--state", "1790").stdout.strip() == "claimed ownercheck 1780 1790"
    assert sorted(claim.refs(1780, str(clones[0] / ".." / "remote.git"))) == []           # no ticket claim


def test_prune_deletes_the_lock_of_a_closed_epic():
    now = 10 * 86400
    tips = {"ownercheck-1780-1781": now - 60, "ownercheck-1800-1801": now - 60, "ownercheck-1900-1901": now - 8 * 86400}
    assert claim.prunable(tips, {1800, 1900}, now) == ["ownercheck-1780-1781", "ownercheck-1900-1901"]


def test_orphans_line_names_the_lock():
    epic = {"number": 5, "title": "Epic: X", "labels": [{"name": "epic"}],
            "body": "## Owner checks\n- After #11, #12: check the button on a phone\n"}
    [line] = start.owner_check_missing({5: epic}, lambda n: [])
    assert "`claim.py 5 --ownercheck --state 11`" in line and "After #11, #12" in line
