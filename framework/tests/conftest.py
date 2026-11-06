"""The tests of the generic tools (#4195): they import the tools by name, also the project tools (release.py)."""
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [ROOT, os.path.join(ROOT, "framework", "tools"), HERE]
sys.path.append(os.path.join(ROOT, "tools"))


@pytest.fixture(autouse=True)
def empty_stdin(monkeypatch):
    """An empty stdin, as in tests/conftest.py (#2510)."""
    monkeypatch.setattr(sys, "stdin", io.StringIO())


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """The result line also with -qq, as in tests/conftest.py (#2510); only once when both folders run."""
    if config.get_verbosity() < -1 and not getattr(config, "result_line", False):
        config.result_line = True
        counts = {k: len(v) for k, v in terminalreporter.stats.items() if k and k != "warnings"}
        terminalreporter.write_line(", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + f" (exit {exitstatus})")
