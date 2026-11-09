"""The failed tests of CI as GitHub annotations (#1443): `ship_pr.py` prints them for a red check run."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from tests import gh_annotations

ROOT = Path(__file__).resolve().parents[1]


def report(nodeid, path, lineno, text):
    crash = SimpleNamespace(message=text)
    return SimpleNamespace(nodeid=nodeid, location=(path, lineno, "x"), longrepr=SimpleNamespace(reprcrash=crash))


def test_a_failed_report_gives_one_escaped_error_line():
    r = report("tests/test_a.py::test_b[1,2]", "tests/test_a.py", 9, "assert 1 == 2\n+  where 100% wrong")
    assert gh_annotations.lines([r]) == [
        "::error file=tests/test_a.py,line=10,title=failed test::tests/test_a.py::test_b[1,2] - assert 1 == 2"]
    assert gh_annotations.escape("a%b\nc") == "a%25b%0Ac"
    assert gh_annotations.escape("a:b,c", prop=True) == "a%3Ab%2Cc"


def test_a_collection_error_has_no_line_and_uses_the_last_line_of_its_text():
    r = SimpleNamespace(nodeid="tests/test_c.py", location=("tests/test_c.py", None, "tests/test_c.py"),
                        longrepr="Traceback ...\nImportError: no module x\n")
    assert gh_annotations.lines([r]) == [
        "::error file=tests/test_c.py,title=failed test::tests/test_c.py - ImportError: no module x"]


def test_more_than_ten_failures_give_nine_lines_and_a_count():
    out = gh_annotations.lines([report(f"t.py::t{i}", "t.py", i, "boom") for i in range(15)])
    assert len(out) == gh_annotations.LIMIT
    assert out[-1] == "::error title=more failed tests::6 more failed tests: see the job log"


def run(tmp_path, github):
    """The output of pytest (with xdist, as in CI) on one red and one green test, with tests/conftest.py loaded."""
    (tmp_path / "test_red.py").write_text("def test_red():\n    assert 1 == 2\n\n\ndef test_green():\n    pass\n")
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"} | {"PYTHONPATH": str(ROOT)}
    if github:
        env["GITHUB_ACTIONS"] = "true"
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "tests.conftest", "-n", "2", "-c", os.devnull,
                           "--rootdir", str(tmp_path), str(tmp_path / "test_red.py")],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120).stdout


def test_pytest_in_github_actions_writes_the_failed_test(tmp_path):
    out = run(tmp_path, github=True)
    errors = [line for line in out.splitlines() if line.startswith("::error")]
    assert errors == ["::error file=test_red.py,line=1,title=failed test::test_red.py::test_red - assert 1 == 2"], out


def test_pytest_outside_github_actions_writes_no_annotation(tmp_path):
    out = run(tmp_path, github=False)
    assert "1 failed" in out and "::error" not in out, out
