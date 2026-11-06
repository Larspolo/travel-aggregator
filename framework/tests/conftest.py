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


def github_write(args, method=None):
    """True for a call that changes the real repository: `gh` other than a plain `gh api` read, or an HTTP request
    with a method other than GET."""
    if method is not None:
        return method.upper() != "GET"
    args = [str(a) for a in args] if isinstance(args, (list, tuple)) else str(args).split()
    if not args or os.path.basename(args[0]) != "gh":
        return False
    if args[1:2] != ["api"]:
        return True
    i = args.index("-X") if "-X" in args else args.index("--method") if "--method" in args else -1
    return (i >= 0 and args[i + 1].upper() != "GET") or any(a in args for a in ("-f", "-F", "--field", "--raw-field",
                                                                                 "--input"))


@pytest.fixture(autouse=True)
def no_github_writes(monkeypatch):
    """No test writes to the real repository of agent.toml. A test that patched `on_github` but not `dashboard.api`
    posted "Started by `run-0`." and `in-progress` on the real issue #8 at each full run (764 comments in aoe2mc, and
    a blocked open ticket in a new project). A test that needs the API patches it; a real write fails here."""
    import subprocess
    import urllib.request
    run, urlopen = subprocess.run, urllib.request.urlopen

    def guarded_run(args, *a, **k):
        if github_write(args):
            raise RuntimeError(f"a test must not write to GitHub: {args}")
        return run(args, *a, **k)

    def guarded_urlopen(req, *a, **k):
        if isinstance(req, urllib.request.Request) and "api.github.com" in req.full_url and github_write((), req.get_method()):
            raise RuntimeError(f"a test must not write to GitHub: {req.get_method()} {req.full_url}")
        return urlopen(req, *a, **k)

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(urllib.request, "urlopen", guarded_urlopen)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """The result line also with -qq, as in tests/conftest.py (#2510); only once when both folders run."""
    if config.get_verbosity() < -1 and not getattr(config, "result_line", False):
        config.result_line = True
        counts = {k: len(v) for k, v in terminalreporter.stats.items() if k and k != "warnings"}
        terminalreporter.write_line(", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + f" (exit {exitstatus})")
