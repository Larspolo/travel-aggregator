"""The install step of the CI job browser retries (#2325)."""

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _install_step() -> str:
    jobs = yaml.safe_load(CI.read_text())["jobs"]
    steps = [s.get("run", "") for s in jobs["browser"]["steps"]]
    found = [r for r in steps if "playwright install --with-deps chromium" in r]
    assert len(found) == 1
    return found[0]


def test_install_step_retries_three_times_with_waits():
    run = _install_step()
    assert "for attempt in 1 2 3" in run
    assert "attempt * 15" in run  # waits of 15 s and then 30 s
    assert 'sleep "$wait"' in run
    assert "exit 0" in run and run.rstrip().endswith("exit 1")
