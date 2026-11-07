"""Each job of ci.yml that runs on a PR gates the merge: Automerge merges only a green CI workflow. So `ship_pr.py`
waits for each of them (`[ci] gates` of `agent.toml`), and the run that wrote the code fixes a red job with its warm
context. With `gates = []`, 3 of the last 20 red CI runs were a red `browser` job after a green `quick` job: the run
reported "Automerge merges it" and stopped, and a cold run took the red PR over (process review 2026-11-07)."""
import pathlib
import tomllib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def pr_jobs():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    return {name for name, job in jobs.items() if "pull_request'" not in str(job.get("if", ""))}


def test_each_pr_job_of_ci_is_a_gate():
    gates = set(tomllib.loads((ROOT / "agent.toml").read_text())["ci"]["gates"])
    missing = pr_jobs() - gates - {"quick"}
    assert not missing, f"add {sorted(missing)} to `[ci] gates` of agent.toml: Automerge needs these PR jobs green"
    assert not gates - pr_jobs(), f"`[ci] gates` names jobs that do not run on a PR: {sorted(gates - pr_jobs())}"
