"""Each Playwright launch in a test has the fallback for CI (#738).

The cloud has Chromium at /opt/pw-browsers/chromium; the CI job `browser` does not. A test that always passes
`executable_path` passes in the cloud and fails in CI (PR #738, 2026-11-07: a red browser job; the verify skill said to
pass the path). This check replaces the line of docs/LEARNINGS.md that #738 added.
"""
from pathlib import Path

GUARDS = ("tests/*.py",)   # ship_pr runs this file for each changed test file
TESTS = Path(__file__).resolve().parent
HINT = ('use `exe = "/opt/pw-browsers/chromium"` and '
        "`p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()`")


def launch_problems(name: str, text: str) -> list[str]:
    """The lines of `text` that pass `executable_path=` with no `os.path.exists` fallback on the same line."""
    return [f"{name}:{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1)
            if "executable_path=" in line and "os.path.exists" not in line and not line.lstrip().startswith("#")]


def test_each_test_launch_has_the_ci_fallback():
    problems = [p for f in sorted(TESTS.glob("*.py")) if f.name != Path(__file__).name
                for p in launch_problems(f.name, f.read_text(encoding="utf-8"))]
    assert problems == [], f"the CI job `browser` has no /opt/pw-browsers: {HINT}\n" + "\n".join(problems)


def test_a_launch_with_no_fallback_is_found():
    text = 'exe = "/opt/pw-browsers/chromium"\nbrowser = p.chromium.launch(executable_path=exe)\n'
    assert launch_problems("t.py", text) == ["t.py:2: browser = p.chromium.launch(executable_path=exe)"]


def test_a_launch_with_the_fallback_passes():
    text = "b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()\n"
    assert launch_problems("t.py", text) == []
