"""The preview gate starts CI for a newer head of main with no run (#2175)."""

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _preview():
    return yaml.safe_load(CI.read_text())["jobs"]["preview"]


def _gate():
    return next(s for s in _preview()["steps"] if s.get("id") == "gate")["run"]


def test_preview_job_may_dispatch():
    assert _preview()["permissions"].get("actions") == "write"


def test_gate_looks_up_runs_of_head():
    run = _gate()
    assert "actions/workflows/ci.yml/runs?head_sha=$head" in run
    assert "total_count" in run


def test_gate_dispatches_only_when_head_has_no_run():
    run = _gate()
    lookup = run.index("head_sha=$head")
    dispatch = run.index("gh workflow run ci.yml")
    assert lookup < dispatch
    assert '[ "$runs" = "0" ]' in run[lookup:dispatch]
    assert "--ref main" in run[dispatch:]


def test_gate_still_skips_old_commit():
    run = _gate()
    assert 'if [ "$head" != "$GITHUB_SHA" ]' in run
    assert "go=false" in run and "go=true" in run
