"""framework/tools/claim.py --fixmain: one run makes the "Fix main" ticket of one break of main (#3480: 8 copies in 6 minutes)."""
import os
import subprocess
import sys

import claim
from test_claim import clones, tool  # noqa: F401 (fixture)

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "claim.py")


def test_one_run_makes_the_fix_main_ticket(clones):  # noqa: F811
    """Three runs of any lane at the same time: one gets the lock. Another break (commit) gives a new lock."""
    procs = [subprocess.Popen([sys.executable, TOOL, "0", "--fixmain", "--state", "b484650"], cwd=d,
                              stdout=subprocess.PIPE, text=True) for d in clones]
    assert sorted(p.wait() for p in procs) == [0, 1, 1]
    again = tool(clones[1], "0", "--fixmain", "--state", "b484650")
    assert again.returncode == 1 and "another run makes the ticket" in again.stdout
    assert tool(clones[2], "0", "--fixmain", "--state", "61f82e1").stdout.strip() == "claimed fixmain 61f82e1"
    assert sorted(claim.refs(0, str(clones[0] / ".." / "remote.git"))) == []               # no ticket claim
