"""The image pulls of CI try again after a reset of Docker Hub (#615): `scripts/retry.sh` and its use in `ci.yml`."""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RETRY = ROOT / "scripts" / "retry.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
GUARDS = ("scripts/retry.sh", ".github/workflows/ci.yml")


def _run(tmp_path, fails):
    """Run retry.sh with a command that fails `fails` times, then passes; return (exit code, tries)."""
    count = tmp_path / "count"
    cmd = f'n=$(( $(cat {count} 2>/dev/null || echo 0) + 1 )); echo $n > {count}; [ $n -gt {fails} ]'
    done = subprocess.run([str(RETRY), "bash", "-c", cmd], env={**os.environ, "RETRY_SLEEP": "0"},
                          capture_output=True, text=True)
    return done.returncode, int(count.read_text())


def test_a_command_that_fails_twice_passes_on_the_third_try(tmp_path):
    assert _run(tmp_path, 2) == (0, 3)


def test_a_command_that_passes_runs_once(tmp_path):
    assert _run(tmp_path, 0) == (0, 1)


def test_a_command_that_always_fails_stops_after_three_tries_with_its_code(tmp_path):
    done = subprocess.run([str(RETRY), "bash", "-c", "exit 7"], env={**os.environ, "RETRY_SLEEP": "0"},
                          capture_output=True, text=True)
    assert done.returncode == 7
    assert done.stderr.count("retry.sh: try") == 2
    code, tries = _run(tmp_path, 5)
    assert (code, tries) == (1, 3)


def _jobs():
    """{job: [lines]} of ci.yml, with no comments and step names (a line with 2 spaces of indent starts a job)."""
    jobs, name = {}, None
    for line in CI.read_text().splitlines():
        if m := re.match(r"^  ([a-z][\w-]*):\s*$", line):
            name = m.group(1)
            jobs[name] = []
        elif name and not line.lstrip().startswith(("#", "- name:", "name:")):
            jobs[name].append(line)
    return jobs


def test_each_pull_of_ci_goes_through_retry():
    for job, lines in _jobs().items():
        for line in lines:
            if re.search(r"docker (compose )?pull\b", line):
                assert "retry.sh docker" in line, f"job {job}: a pull with no scripts/retry.sh (#615): {line.strip()}"


def test_each_job_that_builds_or_starts_pulls_its_images_first():
    for job, lines in _jobs().items():
        starts = [i for i, line in enumerate(lines) if re.search(r"docker (build|compose up|run -d)\b", line)]
        if starts:
            pulls = [i for i, line in enumerate(lines) if "retry.sh docker" in line]
            assert pulls and pulls[0] < starts[0], f"job {job}: pull its images with scripts/retry.sh first (#615)"
            assert any("awk '/^FROM/" in line for line in lines if "retry.sh" in line), \
                f"job {job}: pull the base images of Dockerfile with scripts/retry.sh (#615)"
