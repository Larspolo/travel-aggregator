"""Each test starts with empty limiters (#521): the bad tokens of one test must not lock the API for the next test.

All TestClient requests come from the address "testclient", so the counts of the global limiters (#145, #412) go
from one test to the next in the same worker. This test runs two inner tests in sequence with the real conftest.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INNER = '''
from app.auth import api_limiter, login_limiter, token_limiter


def test_a_fills_the_limiters():
    for _ in range(token_limiter.ADDRESS_MAX):
        token_limiter.failure("testclient")
        login_limiter.failure("testclient")
    for _ in range(api_limiter.MAX):
        api_limiter.hit("token")
    assert token_limiter.retry_after("testclient") > 0


def test_b_starts_with_empty_limiters():
    assert token_limiter.retry_after("testclient") == 0
    assert login_limiter.retry_after("testclient") == 0
    assert api_limiter.hit("token") == 0
'''


def test_a_test_starts_with_the_limiters_of_no_earlier_test(tmp_path):
    shutil.copy(ROOT / "tests" / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_inner.py").write_text(INNER)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:xdist", "-p", "no:randomly",
                             "-p", "no:cacheprovider", "test_inner.py"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
