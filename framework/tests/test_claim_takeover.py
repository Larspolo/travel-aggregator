"""framework/tools/claim.py --takeover: only a stale or released claim, and only one run at the same time (#502)."""
import os
import subprocess
import sys
import time

from test_claim import TOOL, clones, tool  # noqa: F401  (clones is a fixture)


def old(d, *args):
    """Run the tool with a commit time 31 minutes ago: the claim is stale at once."""
    env = dict(os.environ, GIT_COMMITTER_DATE=f"{int(time.time()) - 31 * 60} +0000")
    return subprocess.run([sys.executable, TOOL, *args], cwd=d, capture_output=True, text=True, env=env)


def test_takeover_needs_a_stale_claim(clones):  # noqa: F811
    a, b, _ = clones
    assert tool(a, "8").returncode == 0
    r = tool(b, "8", "--takeover")
    assert r.returncode == 1 and "owned by another run" in r.stdout
    assert old(a, "8", "--beat").returncode == 0                   # last beat 31 minutes ago: a stopped run
    assert tool(b, "8", "--takeover").stdout.strip() == "claimed claim/8-2"
    assert tool(a, "8", "--takeover").returncode == 1              # the new claim is live


def test_one_takeover_wins_at_the_same_time(clones):  # noqa: F811
    a, b, c = clones
    assert old(a, "9").returncode == 0
    procs = [subprocess.Popen([sys.executable, TOOL, "9", "--takeover"], cwd=d, stdout=subprocess.PIPE, text=True)
             for d in (b, c)]
    assert sorted(p.wait() for p in procs) == [0, 1]
