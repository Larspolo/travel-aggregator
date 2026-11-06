"""framework/tools/claim.py: a ticket claim through a git ref, against a local bare repository (no network)."""
import os
import subprocess
import sys

import claim
import pytest

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "claim.py")


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def clones(tmp_path):
    """A bare remote and three clones on the branches run-0, run-1, run-2."""
    remote = tmp_path / "remote.git"
    run("git", "init", "-q", "--bare", str(remote), cwd=tmp_path)
    out = []
    for i in range(3):
        d = tmp_path / f"run{i}"
        run("git", "init", "-q", "-b", f"run-{i}", str(d), cwd=tmp_path)
        run("git", "remote", "add", "origin", str(remote), cwd=d)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            run("git", "config", k, v, cwd=d)
        out.append(d)
    return out


def tool(d, *args):
    return subprocess.run([sys.executable, TOOL, *args], cwd=d, capture_output=True, text=True)


def test_one_claim_wins_at_the_same_time(clones):
    procs = [subprocess.Popen([sys.executable, TOOL, "7"], cwd=d, stdout=subprocess.PIPE, text=True)
             for d in clones]
    codes = sorted(p.wait() for p in procs)
    assert codes == [0, 1, 1]
    assert list(claim.refs(7, str(clones[0] / ".." / "remote.git"))) == [1]


def test_release_and_takeover(clones, monkeypatch):
    a, b, c = clones
    assert tool(a, "5").returncode == 0
    assert tool(b, "5").returncode == 1                         # owned by run-0
    assert tool(b, "5", "--release").returncode != 0            # not the claim of run-1
    assert tool(a, "5", "--release").stdout.strip() == "released claim/5"
    assert tool(b, "5").stdout.strip() == "claimed claim/5-2"   # free again: the next slot
    assert tool(c, "5").returncode == 1
    assert tool(c, "5", "--takeover").returncode == 1           # a live claim: no takeover (#502)
    assert tool(b, "5", "--release").stdout.strip() == "released claim/5-2"
    assert tool(c, "5", "--takeover").stdout.strip() == "claimed claim/5-3"
    monkeypatch.chdir(c)
    assert claim.subject("claim/5-3").startswith("Claim #5 by run-2")
    assert claim.subject("claim/5").startswith("Release #5 by run-0")
    assert sorted(claim.refs(5)) == [1, 2, 3]
    assert sorted(claim.refs(50)) == []                         # claim/5 is no prefix match of claim/50


def test_stale_rule_with_fixed_times():
    """A run that a usage limit stopped at 20:17 (last beat 20:10) is free 30 minutes after its last beat (#231),
    which is before the limit reset (20:30) + 30 minutes. A live run beats again and keeps its ticket."""
    t = lambda hh, mm: (hh * 60 + mm) * 60                                    # noqa: E731
    claim_line, beat = "Claim #9 by run-0 (abc)", t(20, 10)
    assert not claim.stale(claim_line, beat, t(20, 39))
    assert claim.stale(claim_line, beat, t(20, 40))
    assert claim.stale("Beat #9 by run-0", beat, t(21, 0))
    assert not claim.stale("Beat #9 by run-0", t(20, 45), t(21, 0))          # beat after the reset: alive
    assert not claim.stale("Release #9 by run-0", beat, t(23, 0))            # released: free anyway, no takeover


def test_beat_moves_the_claim_time(clones, monkeypatch):
    a, b, _ = clones
    assert tool(a, "6").returncode == 0
    assert tool(b, "6", "--beat").returncode != 0                 # not the claim of run-1
    assert tool(a, "6", "--stale").returncode == 1                # just claimed
    assert tool(a, "6", "--beat").stdout.strip() == "beat claim/6"
    monkeypatch.chdir(a)
    assert claim.subject("claim/6") == "Beat #6 by run-0"
    assert tool(b, "6").returncode == 1                           # a beat is no release
    assert tool(a, "6", "--release").stdout.strip() == "released claim/6"
    assert tool(a, "6", "--stale").returncode == 1                # released: not stale


def test_started_by_comment_of_another_branch():
    """#288: a run commented "Started by" and worked without the claim ref. Its comment blocks the claim for 30 minutes."""
    c = lambda body, at: {"body": body, "created_at": at}                    # noqa: E731
    now = claim.datetime.datetime(2026, 10, 25, 21, 30, tzinfo=claim.datetime.timezone.utc).timestamp()
    comments = [c("Started by `run-0`.\n\n---\nfooter", "2026-10-25T21:23:10Z"), c("A question", "2026-10-25T21:25:00Z")]
    assert claim.started_by_other(comments, "run-1", now) == "run-0"
    assert claim.started_by_other(comments, "run-0", now) is None             # the own comment
    assert claim.started_by_other(comments, "run-1", now + 30 * 60) is None   # older than 30 minutes
    assert claim.started_by_other([c("I started by `x` it", "2026-10-25T21:29:00Z")], "run-1", now) is None


def test_claim_fails_after_a_started_by_comment(clones, monkeypatch):
    a, b, _ = clones
    now = claim.datetime.datetime.now(claim.datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: [] if path.startswith("pulls") else
                        [{"body": "Started by `run-0`.", "created_at": now}])
    monkeypatch.chdir(b)
    assert claim.main(["8"]) == 1                                  # run-0 commented, but has no claim ref
    assert claim.refs(8) == {}
    monkeypatch.chdir(a)
    assert claim.main(["8"]) == 0                                  # the own comment does not block


def test_other_pr_closes_the_ticket():
    pr = lambda n, ref, body, state="open", merged=None: {"number": n, "head": {"ref": ref}, "body": body,  # noqa: E731
                                                          "state": state, "merged_at": merged}
    pulls = [pr(1, "run-1", "Closes #220"), pr(2, "run-0", "Fixes #2200"), pr(3, "run-0", "closes #22", "closed")]
    assert claim.other_pr(pulls, 220, "run-1") is None              # the own PR
    assert claim.other_pr(pulls, 220, "run-0") == 1
    assert claim.other_pr(pulls, 22, "run-1") is None               # closed without a merge
    assert claim.other_pr([pr(4, "run-0", "...\nCloses #22", "closed", "2026-10-25T21:35:00Z")], 22, "run-1") == 4
    assert claim.other_pr([pr(5, "run-0", None)], 22, "run-1") is None
    assert claim.other_pr(pulls, 220, "run-0", taken="run-2") == 1                  # #361: only the taken-over PR
    taken = [pr(6, "run-0", "Closes #22")]
    assert claim.other_pr(taken, 22, "run-1", taken="run-0") is None
    assert claim.other_pr([pr(7, "run-0", "Closes #22", "closed", "2026-10-25T21:35:00Z")], 22, "run-1",
                          taken="run-0") == 7                                      # merged already: stop


def test_guard_before_the_push(clones, monkeypatch):
    a, b, _ = clones
    assert tool(a, "9", "--guard").returncode == 1                 # no claim: stop
    assert tool(a, "9").returncode == 0
    assert tool(b, "9", "--guard").returncode != 0                 # the claim of another run: stop
    assert tool(a, "9", "--guard").stdout.strip() == "beat claim/9, no PR of another branch"
    monkeypatch.chdir(a)
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: [{"number": 283, "head": {"ref": "run-1"}, "body": "Closes #9",
                                                     "state": "closed", "merged_at": "2026-10-25T21:35:00Z"}])
    assert claim.main(["9", "--guard"]) == 1


def test_one_run_handles_a_comment(clones):
    """A second lock of the same owner comment exits 1, also at the same time (#320)."""
    procs = [subprocess.Popen([sys.executable, TOOL, "123456", "--comment"], cwd=d, stdout=subprocess.PIPE, text=True)
             for d in clones]
    assert sorted(p.wait() for p in procs) == [0, 1, 1]
    assert tool(clones[0], "123456", "--comment").returncode == 1
    assert tool(clones[0], "123457", "--comment").stdout.strip() == "claimed comment 123457"
    assert sorted(claim.refs(123456, str(clones[0] / ".." / "remote.git"))) == []     # no ticket claim
