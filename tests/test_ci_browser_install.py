"""The browser install of the CI job browser survives a network failure of the runner (#2325)."""

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _runs() -> list[str]:
    jobs = yaml.safe_load(CI.read_text())["jobs"]
    return [s.get("run", "") for s in jobs["browser"]["steps"]]


def _one(text: str) -> str:
    found = [r for r in _runs() if text in r]
    assert len(found) == 1, found
    return found[0]


def test_browser_download_retries_three_times_with_waits():
    run = _one("playwright install chromium")
    assert "for attempt in 1 2 3" in run
    assert "attempt * 15" in run  # waits of 15 s and then 30 s
    assert 'sleep "$wait"' in run
    assert "exit 0" in run and run.rstrip().endswith("exit 1")


def test_system_packages_have_a_time_limit_and_do_not_fail_the_job():
    run = _one("playwright install-deps chromium")
    assert run.lstrip().startswith("timeout 180 ")
    assert '|| echo "::warning::' in run


def test_no_step_installs_the_packages_with_no_time_limit():
    assert not [r for r in _runs() if "--with-deps" in r]
