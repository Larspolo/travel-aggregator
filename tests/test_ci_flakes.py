"""Two CI flakes that made a run start the failed jobs again (#2488).

1. The job `docker`: a timeout of `apt.postgresql.org` in the Dockerfile gave "Unable to locate package
   postgresql-client-16". Each `apt-get` of the Dockerfile now tries longer, and each `update` fails at the fetch.
2. The job `browser`: a GitHub error of the screenshot upload failed a job whose tests passed. The screenshots are
   only for a person, so the upload cannot fail the job; the test step still can.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
CI = ROOT / ".github" / "workflows" / "ci.yml"
GUARDS = ("Dockerfile", ".github/workflows/ci.yml")


def _apt_calls():
    text = DOCKERFILE.read_text()
    return text, re.findall(r"apt-get\s+([^&\\\n]*?)\b(update|install)\b", text)


def test_each_apt_fetch_of_the_dockerfile_tries_again():
    text, calls = _apt_calls()
    assert re.search(r'^ARG APT_RETRY="-o Acquire::Retries=\d+"', text, re.M), "Dockerfile: ARG APT_RETRY (#2488)"
    assert len([c for c in calls if c[1] == "update"]) >= 2, calls
    for opts, verb in calls:
        assert "$APT_RETRY" in opts, f"apt-get {verb} with no $APT_RETRY: a timeout fails the build (#2488)"
        if verb == "update":
            assert "--error-on=any" in opts, "apt-get update with no --error-on=any: the error comes too late (#2488)"


def _steps(job):
    """The steps of a job of ci.yml as text blocks."""
    lines = CI.read_text().splitlines()
    start = lines.index(f"  {job}:")
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  [a-z][\w-]*:\s*$", lines[i])), len(lines))
    return re.split(r"\n(?=      - )", "\n".join(lines[start:end]))


def test_the_screenshot_upload_cannot_fail_the_browser_job():
    steps = _steps("browser")
    uploads = [s for s in steps if "actions/upload-artifact" in s]
    assert uploads, "the job browser has no screenshot upload"
    for step in uploads:
        assert re.search(r"^\s+continue-on-error: true\b", step, re.M), "upload-artifact with no continue-on-error"
    tests = [s for s in steps if "pytest" in s]
    assert tests and not any("continue-on-error" in s for s in tests), "the test step must fail the job"
