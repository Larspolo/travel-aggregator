"""A stuck ticket whose PR only waits for its quick CI or for Automerge gives no takeover (#4932): 10 of 14 takeovers
"after the report" closed by the Automerge merge 0 to 18 minutes later. A green PR starts the Automerge sweep."""
import pacer

NOW = 2_000_000_000
OLD = "2033-05-18T01:00:00Z"            # about 2 hours before NOW: no claim ref, no change for 30 minutes


def issue(n):
    return {"number": n, "title": f"T{n}", "labels": [{"name": "in-progress"}], "updated_at": OLD}


def pr(n, sha, labels=()):
    return {"number": 100 + n, "body": f"Closes #{n}", "head": {"ref": f"agent/{n}", "sha": sha},
            "labels": [{"name": x} for x in labels]}


def check(name, status="completed", conclusion="success"):
    return {"name": name, "status": status, "conclusion": None if status != "completed" else conclusion}


CHECKS = {"run": [check("quick", "in_progress"), check("lint")],
          "queued": [check("quick", "queued")],
          "green": [check("quick"), check("lint", "in_progress")],
          "red": [check("quick"), check("lint", conclusion="failure")],
          "redquick": [check("quick", conclusion="failure")],
          "none": [check("lint")]}


def run(cases):
    """cases: {ticket: (sha or None, labels)}. (taken over tickets, number of sweeps)."""
    sweeps = []
    issues = [issue(n) for n in cases]
    pulls = [pr(n, sha, labels) for n, (sha, labels) in cases.items() if sha]
    got = pacer.stuck(issues, [], NOW, pulls, checks=CHECKS.__getitem__, start_sweep=lambda: sweeps.append(1))
    return {i["number"]: t for i, t in got}, len(sweeps)


def test_a_running_or_green_quick_check_gives_no_takeover():
    assert run({1: ("run", ()), 2: ("queued", ())}) == ({}, 0)
    assert run({3: ("green", ()), 4: ("green", ())}) == ({}, 1)            # one sweep per cycle


def test_red_conflict_or_no_pr_gives_a_takeover_as_before():
    got, sweeps = run({5: ("red", ()), 6: ("redquick", ()), 7: ("green", ("conflict",)), 8: (None, ()),
                       9: ("none", ())})
    assert got == {5: "PR #105 agent/5", 6: "PR #106 agent/6", 7: "PR #107 agent/7", 8: "no PR",
                   9: "PR #109 agent/9"}
    assert sweeps == 0


def test_a_dry_run_sends_no_sweep():
    assert pacer.stuck([issue(3)], [], NOW, [pr(3, "green")], checks=CHECKS.__getitem__, start_sweep=None) == []
