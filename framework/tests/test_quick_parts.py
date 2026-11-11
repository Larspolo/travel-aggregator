"""The job `quick` of ci.yml is a matrix of 2 jobs (#1077): its check runs are `quick (1)` and `quick (2)`. Each reader
of the check `quick` takes both parts as one check: green only when both parts are green, red when one part is red,
and "not queued yet" when a part is missing. An older commit has one check run `quick`."""
import json
import os
import re
import subprocess

import cycle_start
import dashboard
import health
import pacer
import pytest
import ship_pr as ship
import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
AUTOMERGE = os.path.join(ROOT, ".github", "workflows", "automerge.yml")
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")


def run(name, conclusion="success", status="completed", id=0):
    return {"id": id, "name": name, "status": status, "conclusion": conclusion, "check_suite": {"id": 1}}


ONE = run("quick (1)", id=1)
TWO = run("quick (2)", id=2)
TWO_RED = run("quick (2)", "failure", id=3)
TWO_RUNS = run("quick (2)", None, "in_progress", id=4)


def green(checks):
    """The result of the GREEN filter of the Automerge sweep, as jq runs it."""
    flt = re.search(r"^\s*GREEN='(.*?)'$", open(AUTOMERGE).read(), re.M | re.S).group(1)
    return subprocess.run(["jq", "-e", flt], input=json.dumps(checks), capture_output=True, text=True).returncode == 0


@pytest.mark.parametrize("checks, want, state", [
    ([ONE, TWO], True, "green"),                          # both parts are green
    ([TWO_RED, ONE], False, None),                        # a red part 2 is red
    ([ONE, TWO_RUNS], False, "run"),                      # part 2 still runs
    ([ONE], False, None),                                 # part 2 is missing: not queued yet
    ([run("quick")], True, "green"),                      # an older commit: one check `quick`
    ([ONE, TWO, run("quickly")], True, "green"),          # not a part of `quick`
    ([ONE, run("quick (2)", "cancelled")], False, None),  # a cancelled part is not green
])
def test_the_readers_merge_the_parts(checks, want, state):
    assert green(checks) is want
    assert pacer.ci_wait({"labels": []}, checks) == state
    assert ship.quick_green(checks) is want
    assert cycle_start.quick_green([(c["name"], c["status"], c["conclusion"]) for c in checks]) is want


def test_quick_run_gives_the_failed_part_first():
    assert ship.quick_run([ONE, TWO_RED]) == TWO_RED          # its id gives the failed steps (ship_pr.failures)
    assert ship.quick_run([ONE, TWO_RUNS]) == TWO_RUNS
    assert ship.quick_run([ONE]) is None
    assert ship.quick_run([]) is None
    assert ship.quick_run([TWO, TWO_RED, ONE]) == TWO        # newest first: a green re-run of part 2 counts


def test_quick_reads_all_check_runs_of_the_commit(monkeypatch):
    paths = []
    monkeypatch.setattr(dashboard, "api", lambda path: paths.append(path) or {"check_runs": [ONE, TWO_RED]})
    assert ship.quick("abc") == TWO_RED
    assert paths == ["commits/abc/check-runs?per_page=100&filter=latest"]   # not `check_name=quick`: it misses `quick (1)`


def test_the_matrix_of_ci_has_quick_parts_jobs():
    job = yaml.safe_load(open(CI))["jobs"]["quick"]
    assert job["strategy"]["matrix"]["shard"] == list(range(1, ship.QUICK_PARTS + 1))
    tests = next(s for s in job["steps"] if s.get("name") == "Fast tests")
    assert f"--shard ${{{{ matrix.shard }}}}/{ship.QUICK_PARTS}" in tests["run"]
    lint = next(s for s in job["steps"] if s.get("name") == "Lint")
    assert lint["if"] == "matrix.shard == 1"
    assert f"else {ship.QUICK_PARTS} end" in open(AUTOMERGE).read()


def test_the_steps_of_the_parts_count_as_one_job():
    def job(name, minutes):
        return dict(name=name, steps=[dict(name="Fast tests", started_at="2026-11-08T13:00:00Z",
                                           completed_at=f"2026-11-08T13:{minutes:02d}:00Z")])
    assert health.slow_steps([job("quick (1)", 1), job("quick (2)", 3)], 3) == [(2.0, "quick / Fast tests")]
